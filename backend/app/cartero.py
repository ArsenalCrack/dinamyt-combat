"""
El cartero: sube solos a internet los resultados del PC del evento (F8).

── Qué automatiza, y qué no ──

Lo que automatiza es el USB (Reportes → Exportar → llevar el archivo → Importar
en internet), no la dirección: sigue siendo un solo sentido y solo suben
podios y rankings (`PLAN-SINCRONIZACION-LOCAL-ONLINE.md`, «El viaje de
vuelta»). Y el USB se queda: es el plan B del día que esto no funcione.

── Con qué se identifica: con la sesión del propio administrador ──

El destino (`POST /api/resultados/importar` de la instalación de internet)
exige un administrador, y un programa no puede teclear una contraseña. El plan
decidió **no guardar ninguna llave en el PC del evento** (F8, «Cómo se
identifica»): cuando vuelve la red, el administrador entra a esta instalación
con su cuenta de DINAMYT, y ese pase —que dura minutos y vive solo en la
memoria de este proceso, nunca en disco— es el que abre la sesión allá. Si
nadie entra, la cola espera. No se pierde nada.

── Qué hace falta en el `.env` del PC del evento ──

  · `CAMPEONATOS_ONLINE_URL` — la instalación de internet (su raíz, sin
    `/api`). Sin ella esto está apagado, y se dice (ver `estado`).
  · `ECOSYSTEM_JWKS_URL` — para que «Entrar con DINAMYT» funcione aquí cuando
    hay red. Sin internet no molesta: el QR de los jueces ya no sale a la red
    (`identidad.verificar_pase`) y el login con contraseña nunca salió.

── Cuándo NO sube ──

Nunca mientras haya una llave activa (un combate en marcha): subir compite por
la red y por la base con el tatami, y el tatami gana siempre.
"""

import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .extensions import db

log = logging.getLogger(__name__)

# Cuánto se espera a la instalación de internet en cada petición.
ESPERA_SEG = 15
# Entre intentos fallidos, esperas que crecen: 1, 2, 4, 8… minutos, hasta una hora.
ESPERA_MAX_MIN = 60
# Cada cuánto vuelve a mirar el hilo de fondo mientras haya pase y pendientes.
VUELTA_SEG = 60
# El nombre de la cookie de sesión de la instalación de internet (config.py).
COOKIE_SESION = "dinamyt_session"

# El pase del administrador que entró con DINAMYT. SOLO en memoria.
_pase = {"token": None, "exp": 0.0, "email": None}
_lock = threading.Lock()
_hilo = {"vivo": False}
# Una pasada a la vez. El hilo de fondo y el botón «Subir ahora» se podían
# cruzar: los dos creaban la fila del mismo `export_uuid` (única) y uno de los
# dos reventaba — el botón con un 500, o el hilo muriéndose en silencio.
_vaciando = threading.Lock()


def destino_configurado():
    """Lo que dice `CAMPEONATOS_ONLINE_URL`, sin juzgarlo."""
    return os.getenv("CAMPEONATOS_ONLINE_URL", "").strip().rstrip("/")


def _es_seguro(url):
    """https, o http solo hacia este mismo PC (pruebas, un ensayo en casa)."""
    partes = urlparse(url)
    if partes.scheme == "https":
        return bool(partes.hostname)
    return partes.scheme == "http" and partes.hostname in ("localhost", "127.0.0.1", "::1")


def destino():
    """La raíz de la instalación de internet, o cadena vacía si no hay.

    Un destino en `http://` cuenta como ninguno: lo primero que viaja es el
    pase de DINAMYT del administrador, y en claro lo lee cualquiera en la red
    del evento. El arranque lo dice (`_decir_como_quedo_el_ecosistema`).
    """
    url = destino_configurado()
    return url if url and _es_seguro(url) else ""


def _ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── El pase ─────────────────────────────────────────────────────────────────

def recordar_pase(usuario, token, claims, app=None):
    """Lo llama la entrada con DINAMYT (`api/auth.py`) cuando entra un admin.

    Solo si hay destino: en la instalación de internet no hay nada que subir y
    no tiene sentido tener el pase de nadie en memoria. Arranca el hilo de
    fondo que vacía la cola mientras el pase dure.
    """
    if not destino() or not usuario or not usuario.tiene_rol("admin"):
        return False
    with _lock:
        _pase["token"] = token
        _pase["exp"] = float((claims or {}).get("exp") or 0)
        _pase["email"] = usuario.email
    if app is not None:
        _arrancar_hilo(app)
    return True


def _pase_vivo():
    """(token, email) del pase si le queda al menos un minuto, o (None, None)."""
    with _lock:
        if _pase["token"] and _pase["exp"] - time.time() > 60:
            return _pase["token"], _pase["email"]
    return None, None


def olvidar_pase(email=None):
    """Se olvida el pase. Con `email`, solo si es el de esa persona."""
    with _lock:
        if email is not None and _pase["email"] != email:
            return
        _pase.update({"token": None, "exp": 0.0, "email": None})


# ── Qué hay pendiente ───────────────────────────────────────────────────────

def huella(sobre):
    """sha256 de lo que se publica (sin la fecha de exportación, que cambia sola)."""
    esencial = {k: sobre.get(k) for k in ("resultados", "categorias", "tatamis")}
    esencial["nombre"] = (sobre.get("campeonato") or {}).get("nombre")
    return hashlib.sha256(
        json.dumps(esencial, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def pendientes():
    """[(campeonato, sobre, fila)] de los que tienen resultados que no llegaron."""
    from .api.resultados import _contar_resultados, sobre_de_resultados
    from .models.campeonato import Campeonato
    from .models.subida import SubidaResultados

    salida = []
    for camp in Campeonato.query.order_by(Campeonato.id).all():
        if _contar_resultados(camp.id) == 0:
            continue
        sobre = sobre_de_resultados(camp)
        fila = SubidaResultados.query.filter_by(export_uuid=sobre["export_uuid"]).first()
        if fila is not None and fila.huella_enviada == huella(sobre):
            continue
        salida.append((camp, sobre, fila))
    return salida


def hay_combate_en_marcha():
    from .models.llave import Llave

    return Llave.query.filter(Llave.estado == "activa").first() is not None


# ── Enviar ──────────────────────────────────────────────────────────────────

def _enviar_http(metodo, url, cabeceras, cuerpo=None):
    """(código, [(cabecera, valor)], cuerpo_dict). Aparte para sustituirlo en pruebas.

    Las cabeceras van como LISTA de pares y no como diccionario: la sesión de
    internet llega en dos `Set-Cookie` (la sesión y la de CSRF), y un
    diccionario se queda con una sola — a veces la que no es.
    """
    datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
    peticion = Request(url, data=datos, headers=cabeceras, method=metodo)
    try:
        with urlopen(peticion, timeout=ESPERA_SEG) as respuesta:
            texto = respuesta.read().decode("utf-8") or "{}"
            return respuesta.status, list(respuesta.headers.items()), json.loads(texto)
    except HTTPError as exc:
        try:
            cuerpo_error = json.loads(exc.read().decode("utf-8") or "{}")
        except ValueError:
            cuerpo_error = {}
        return exc.code, list((exc.headers or {}).items()), cuerpo_error


def _sesion_en_internet(pase):
    """El token de sesión de la instalación de internet, abierto con el pase."""
    codigo, cabeceras, cuerpo = _enviar_http(
        "POST", f"{destino()}/api/auth/sesion",
        {"Authorization": f"Bearer {pase}", "Content-Type": "application/json"},
    )
    if codigo != 200:
        raise RuntimeError(cuerpo.get("error") or f"La sesión en internet respondió {codigo}.")
    galletas = SimpleCookie()
    for nombre, valor in cabeceras:
        if nombre.lower() == "set-cookie":
            galletas.load(valor)
    sesion = galletas.get(COOKIE_SESION)
    if sesion is None or not sesion.value:
        raise RuntimeError("La instalación de internet no devolvió una sesión.")
    return sesion.value


def _anotar_fallo(fila, error):
    fila.intentos = (fila.intentos or 0) + 1
    fila.ultimo_error = str(error)[:500]
    espera = min(2 ** (fila.intentos - 1), ESPERA_MAX_MIN)
    fila.proximo_intento_at = _ahora() + timedelta(minutes=espera)


def vaciar(forzar=False):
    """
    Una pasada: intenta subir todo lo pendiente. Devuelve el `estado()` final.

    Sin destino, sin pase o con un combate en marcha no hace nada, y el estado
    dice por qué. `forzar` salta la espera entre intentos (el botón «Subir
    ahora»); nunca salta lo del combate. Si ya hay otra pasada en curso, no
    espera a que acabe: lo dice («subiendo») y el número baja solo.
    """
    if not _vaciando.acquire(blocking=False):
        return estado("subiendo")
    try:
        return _vaciar(forzar)
    finally:
        _vaciando.release()


def _vaciar(forzar):
    from .models.subida import SubidaResultados

    if not destino():
        return estado("sin_destino")
    pase, email = _pase_vivo()
    if not pase:
        return estado("sin_sesion")
    if hay_combate_en_marcha():
        return estado("en_combate")

    lista = pendientes()
    if not lista:
        return estado()

    sesion = None
    for camp, sobre, fila in lista:
        if fila is None:
            fila = SubidaResultados(export_uuid=sobre["export_uuid"], intentos=0)
            db.session.add(fila)
        fila.campeonato_id = camp.id
        fila.nombre = camp.nombre
        if not forzar and fila.proximo_intento_at and fila.proximo_intento_at > _ahora():
            continue
        fila.ultimo_intento_at = _ahora()
        try:
            if sesion is None:
                sesion = _sesion_en_internet(pase)
            codigo, _, cuerpo = _enviar_http(
                "POST", f"{destino()}/api/resultados/importar",
                {"Authorization": f"Bearer {sesion}", "Content-Type": "application/json"},
                sobre,
            )
            if codigo != 200:
                raise RuntimeError(cuerpo.get("error") or f"Internet respondió {codigo}.")
        except (RuntimeError, URLError, OSError, ValueError) as exc:
            _anotar_fallo(fila, exc)
            log.warning("[subida] %s no subió: %s", camp.nombre, exc)
            db.session.commit()
            continue
        fila.huella_enviada = huella(sobre)
        fila.enviado_at = _ahora()
        fila.enviado_por = email
        fila.intentos = 0
        fila.ultimo_error = None
        fila.proximo_intento_at = None
        db.session.commit()
        log.info("[subida] %s subió a internet (%s).", camp.nombre, email)
    return estado()


def estado(motivo=None):
    """Lo que enseña `/admin`. `motivo` = por qué no se subió en esta pasada."""
    from .models.subida import SubidaResultados

    lista = pendientes() if destino() or SubidaResultados.query.first() else []
    filas = SubidaResultados.query.all()
    intentos = [f.ultimo_intento_at for f in filas if f.ultimo_intento_at]
    errores = [f for f in filas if f.ultimo_error]
    pase, _ = _pase_vivo()
    if motivo is None:
        if not destino():
            motivo = "sin_destino"
        elif lista and not pase:
            motivo = "sin_sesion"
        elif lista and hay_combate_en_marcha():
            motivo = "en_combate"
    return {
        "destino": destino() or None,
        "pendientes": [
            {"campeonato_id": c.id, "nombre": c.nombre, "export_uuid": s["export_uuid"]}
            for c, s, _ in lista
        ],
        "subidos": [f.to_dict() for f in filas if f.enviado_at],
        "ultimo_intento_at": max(intentos).isoformat() + "Z" if intentos else None,
        "ultimo_error": errores[-1].ultimo_error if errores else None,
        "sesion_viva": bool(pase),
        "motivo": motivo,
    }


# ── El hilo de fondo ────────────────────────────────────────────────────────

def _arrancar_hilo(app):
    """Vacía la cola en segundo plano mientras el pase dure. Uno solo a la vez."""
    with _lock:
        if _hilo["vivo"]:
            return
        _hilo["vivo"] = True

    def trabajar():
        try:
            while True:
                with app.app_context():
                    pase, _ = _pase_vivo()
                    if not pase:
                        return
                    resultado = vaciar()
                    db.session.remove()
                if not resultado["pendientes"] and resultado["motivo"] is None:
                    return
                time.sleep(VUELTA_SEG)
        except Exception as exc:  # noqa: BLE001 — un hilo que muere no avisa a nadie
            log.warning("[subida] el cartero se detuvo: %s", exc)
        finally:
            with _lock:
                _hilo["vivo"] = False

    threading.Thread(target=trabajar, name="cartero", daemon=True).start()
