"""
LA PUBLICACIÓN EN VIVO — el PC del evento publica hacia arriba (decisión 9).

── El problema ──

Hasta el 1 oct 2026 los resultados subían AL FINAL (F8, `app/cartero.py`):
cuando volvía la red y el admin entraba con su cuenta de DINAMYT. Durante el
evento el público no veía nada en `campeonatos.dinamyt.org/resultados`.

── Lo que NO es: sincronización ──

El PC del evento sigue siendo el único que escribe, y la VPS solo recibe. El
modo de fallo es «el público ve resultados de hace veinte minutos», nunca «se
para el campeonato». Las cinco reglas:

  1. **Solo hacia arriba.** Durante el evento el PC no descarga nada.
  2. **Instantánea completa** (`sobre_de_resultados`, la MISMA del USB y de
     F8), nunca incrementos: mandarla dos veces da igual.
  3. **Nunca en el camino de una petición**: un hilo de fondo con un tope de
     espera corto. (En el PC el backend corre en modo `threading`, no con
     eventlet: un DNS que no resuelve espera en su hilo y no para a nadie.)
  4. **La VPS en solo lectura para ese campeonato**: la llave solo vale con el
     candado de sede puesto (`app/sede.py`).
  5. **El público ve la hora del dato**: «Resultados a las 11:42», no «en
     vivo» (`ResultadoPublicado.datos_de`).

Y dos detalles: la VPS descarta lo que llegue más viejo que lo que ya tiene
(con red mala la de las 11:40 puede llegar después de la de las 11:45), y el
PC no reenvía lo que ya llegó (la misma huella que F8, en la misma tabla).

── Con qué credencial: una llave por campeonato (la opción B) ──

F8 sube con la sesión del admin, que dura media hora: publicar durante horas no
puede depender de que alguien tenga una sesión abierta en el PC. La llave:

  · **La emite la instalación de internet al ceder la sede**, y viaja en el
    paquete «para el evento». Cada bajada mientras siga cedido lleva la misma
    llave y alarga su plazo.
  · **Solo sirve para publicar los resultados de ESE campeonato**, y solo
    mientras siga cedido y dentro de su plazo (`PUBLICAR_LLAVE_DIAS`, 4 por
    defecto: un fin de semana con la víspera).
  · **No se guarda en internet**: se deriva (HMAC con `JWT_SECRET_KEY`) del
    campeonato y de su generación. Devolverlo a la nube o «Retirar la llave»
    sube la generación, y la llave vieja deja de valer para siempre.
  · Es la excepción acotada a «nada guardado en el PC»: lo peor que permite es
    publicar resultados falsos de un evento un fin de semana, que la siguiente
    instantánea buena pisa — y el nombre que se enseña es el de internet, no el
    que diga el archivo.

── Qué hace falta en el `.env` del PC del evento ──

El mismo `CAMPEONATOS_ONLINE_URL` de F8 (https). `PUBLICAR_MINUTOS` (3 por
defecto, 0 = apagado) dice cada cuánto.
"""

import base64
import hashlib
import hmac
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.error import URLError

from flask import current_app

from .extensions import db

log = logging.getLogger(__name__)

# Cuánto vale la llave desde la última bajada «para el evento».
DIAS_POR_DEFECTO = 4
# Cada cuánto publica el PC del evento.
MINUTOS_POR_DEFECTO = 3
# Lo que se espera a internet en cada envío: corto, que hay otra vuelta luego.
ESPERA_SEG = 10
# La cabecera con la que viaja la llave. No es `Authorization` a propósito: esa
# la lee `verify_jwt_in_request` en cada petición (`registrar_contexto_rls`).
CABECERA = "X-Llave-Publicacion"
ENVIADO_POR = "publicación en vivo"


def _ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _utc_sin_zona(dt):
    if dt is not None and dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def instante(texto):
    """Un ISO 8601 como datetime UTC sin zona, o None si no se entiende."""
    if not isinstance(texto, str) or not texto.strip():
        return None
    try:
        dt = datetime.fromisoformat(texto.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt
    return _utc_sin_zona(dt)


def _iso(dt):
    return dt.replace(tzinfo=timezone.utc).isoformat() if dt else None


def _dias():
    try:
        return max(1, int(os.getenv("PUBLICAR_LLAVE_DIAS", str(DIAS_POR_DEFECTO))))
    except ValueError:
        return DIAS_POR_DEFECTO


# ═══════════════════════════════════════════════════════════════════════════
#  En la instalación de INTERNET: la llave
# ═══════════════════════════════════════════════════════════════════════════

def llave_de(camp):
    """La llave de publicación del campeonato en su generación actual."""
    secreto = str(current_app.config.get("JWT_SECRET_KEY") or "").encode("utf-8")
    mensaje = (
        f"dinamyt-publicar-en-vivo|{camp.id}|{camp.export_uuid}|{camp.publicar_gen or 0}"
    ).encode("utf-8")
    firma = hmac.new(secreto, mensaje, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(firma).rstrip(b"=").decode("ascii")


def entregar_llave(camp):
    """Lo que viaja en el paquete para publicar en vivo, o None.

    Solo con el candado de sede puesto: un campeonato que se opera aquí no
    tiene nada que recibir. Cada bajada mientras siga cedido alarga el plazo
    (la de la víspera y la de la mañana llevan la misma llave). El llamador
    hace el commit.
    """
    from .sede import en_otra_sede
    from .uid import nuevo_uid

    if not en_otra_sede(camp):
        return None
    if not camp.export_uuid:
        camp.export_uuid = nuevo_uid()
    hasta = _ahora() + timedelta(days=_dias())
    if camp.publicar_hasta is None or _utc_sin_zona(camp.publicar_hasta) < hasta:
        camp.publicar_hasta = hasta
    return {
        "llave": llave_de(camp),
        "hasta": _iso(_utc_sin_zona(camp.publicar_hasta)),
        "export_uuid": camp.export_uuid,
    }


def llave_vigente(camp):
    """¿Se aceptan instantáneas para este campeonato ahora mismo?"""
    from .sede import en_otra_sede

    hasta = _utc_sin_zona(getattr(camp, "publicar_hasta", None))
    return en_otra_sede(camp) and hasta is not None and hasta > _ahora()


def llave_valida(camp, llave):
    """La llave es la de este campeonato, en su generación, y sigue vigente."""
    if camp is None or not isinstance(llave, str) or not llave:
        return False
    return llave_vigente(camp) and hmac.compare_digest(llave, llave_de(camp))


def retirar_llave(camp):
    """La llave entregada deja de valer para siempre. El llamador hace commit."""
    camp.publicar_gen = (camp.publicar_gen or 0) + 1
    camp.publicar_hasta = None


# ═══════════════════════════════════════════════════════════════════════════
#  En el PC del EVENTO: guardarla y publicar
# ═══════════════════════════════════════════════════════════════════════════

def guardar_llave(camp, publicacion):
    """Guarda la llave que trae el paquete. Devuelve hasta cuándo vale, o None.

    Un paquete sin llave (una copia de prueba, o uno de antes de la versión 8)
    no borra la que hubiera: la de la víspera sigue valiendo si la de la mañana
    se bajó sin marcar.
    """
    if not isinstance(publicacion, dict):
        return None
    llave = publicacion.get("llave")
    hasta = instante(publicacion.get("hasta"))
    if not isinstance(llave, str) or not llave.strip() or len(llave) > 100 or hasta is None:
        return None
    camp.publicar_llave = llave.strip()
    camp.publicar_hasta = hasta
    return hasta


# Lo que pasó en cada campeonato, SOLO en memoria: lo que enseña `/admin`.
# {camp_id: {"ok_at", "intento_at", "error", "rechazada"}}. Se pierde al
# reiniciar, y no importa: en la primera vuelta se sabe otra vez.
_estado = {}
_lock = threading.Lock()
_hilo = {"vivo": False}


def _minutos():
    try:
        return int(os.getenv("PUBLICAR_MINUTOS", str(MINUTOS_POR_DEFECTO)))
    except ValueError:
        return MINUTOS_POR_DEFECTO


def _rechazada(camp):
    with _lock:
        info = _estado.get(camp.id) or {}
        return info.get("rechazada") == camp.publicar_llave


def activa_aqui(camp):
    """¿Este campeonato se está publicando en vivo desde este PC?

    Mientras sí, la cola de F8 no lo cuenta como pendiente (`cartero.pendientes`):
    entre una instantánea y la siguiente diría «1 pendiente · entra con DINAMYT»
    cada tres minutos, en mitad del evento. Cuando la llave caduca, se retira o
    no hay destino, F8 vuelve a encargarse, como siempre.
    """
    from . import cartero

    hasta = _utc_sin_zona(camp.publicar_hasta)
    return bool(
        cartero.destino()
        and camp.publicar_llave
        and hasta is not None and hasta > _ahora()
        and not _rechazada(camp)
    )


def _anotar(camp_id, **cambios):
    with _lock:
        _estado.setdefault(camp_id, {}).update(cambios)


def publicar():
    """Una vuelta: manda la instantánea de cada campeonato que tiene llave.

    Comparte el candado de F8 (`cartero._vaciando`): los dos escriben la fila
    de `SubidaResultados` del mismo `export_uuid`, que es única. Si F8 está
    subiendo, esta vuelta se salta y ya habrá otra.
    """
    from . import cartero
    from .api.resultados import _contar_resultados, sobre_de_resultados
    from .models.campeonato import Campeonato
    from .models.subida import SubidaResultados

    destino = cartero.destino()
    if not destino:
        return estado_local()
    if not cartero._vaciando.acquire(blocking=False):
        return estado_local()
    try:
        campeonatos = (
            Campeonato.query.filter(Campeonato.publicar_llave.isnot(None))
            .order_by(Campeonato.id).all()
        )
        for camp in campeonatos:
            if not activa_aqui(camp) or _contar_resultados(camp.id) == 0:
                continue
            sobre = sobre_de_resultados(camp)
            huella = cartero.huella(sobre)
            fila = SubidaResultados.query.filter_by(export_uuid=sobre["export_uuid"]).first()
            if fila is not None and fila.huella_enviada == huella:
                continue
            _anotar(camp.id, intento_at=_ahora())
            try:
                codigo, _, cuerpo = cartero._enviar_http(
                    "POST", f"{destino}/api/resultados/en-vivo",
                    {CABECERA: camp.publicar_llave, "Content-Type": "application/json"},
                    sobre, espera=ESPERA_SEG,
                )
            except (URLError, OSError, ValueError) as exc:
                _anotar(camp.id, error=str(exc)[:300])
                log.info("[en vivo] %s no se publicó: %s", camp.nombre, exc)
                continue
            if codigo == 401:
                # Se retiró, caducó o el campeonato volvió a la nube: no se
                # insiste con esta llave. F8 se encarga del resto, al final.
                _anotar(camp.id, rechazada=camp.publicar_llave,
                        error=cuerpo.get("error") or "Internet rechazó la llave.")
                log.warning("[en vivo] %s: internet rechazó la llave.", camp.nombre)
                continue
            if codigo != 200:
                _anotar(camp.id, error=cuerpo.get("error") or f"Internet respondió {codigo}.")
                continue
            if fila is None:
                fila = SubidaResultados(export_uuid=sobre["export_uuid"], intentos=0)
                db.session.add(fila)
            fila.campeonato_id = camp.id
            fila.nombre = camp.nombre
            fila.huella_enviada = huella
            fila.enviado_at = fila.ultimo_intento_at = _ahora()
            fila.enviado_por = ENVIADO_POR
            fila.intentos = 0
            fila.ultimo_error = None
            fila.proximo_intento_at = None
            db.session.commit()
            _anotar(camp.id, ok_at=_ahora(), error=None)
    finally:
        cartero._vaciando.release()
    return estado_local()


def estado_local():
    """Lo que enseña `/admin` en el PC: qué se publica en vivo y cómo va."""
    from . import cartero
    from .models.campeonato import Campeonato

    salida = []
    hay_destino = bool(cartero.destino())
    for camp in (
        Campeonato.query.filter(Campeonato.publicar_llave.isnot(None))
        .order_by(Campeonato.id).all()
    ):
        hasta = _utc_sin_zona(camp.publicar_hasta)
        with _lock:
            info = dict(_estado.get(camp.id) or {})
        salida.append({
            "campeonato_id": camp.id,
            "nombre": camp.nombre,
            "hasta": _iso(hasta),
            "vigente": bool(hasta and hasta > _ahora()),
            "activa": activa_aqui(camp),
            "rechazada": info.get("rechazada") == camp.publicar_llave,
            "sin_destino": not hay_destino,
            "ultimo_envio_at": _iso(info.get("ok_at")),
            "ultimo_intento_at": _iso(info.get("intento_at")),
            "ultimo_error": info.get("error"),
        })
    return salida


def iniciar_publicacion(app):
    """Arranca el hilo que publica cada `PUBLICAR_MINUTOS` (PC del evento)."""
    from . import cartero

    minutos = _minutos()
    if minutos <= 0:
        print("  [OFF] Publicación en vivo desactivada (PUBLICAR_MINUTOS=0)")
        return
    if not cartero.destino():
        # Sin destino no hay a dónde publicar; el arranque de F8 ya dice por qué.
        return
    with _lock:
        if _hilo["vivo"]:
            return
        _hilo["vivo"] = True

    def ciclo():
        while True:
            try:
                with app.app_context():
                    publicar()
                    db.session.remove()
            except Exception as exc:  # noqa: BLE001 — un hilo que muere no avisa a nadie
                log.warning("[en vivo] la vuelta falló: %s", exc)
            time.sleep(minutos * 60)

    threading.Thread(target=ciclo, daemon=True, name="publicacion-en-vivo").start()
    print(
        f"  [OK] Publicación en vivo: cada {minutos} min, de los campeonatos que "
        f"traigan llave en su paquete, a {cartero.destino()}"
    )
