"""
Socket.IO Namespace: /combate  v2
Maneja la comunicación en tiempo real para los combates.

Novedades v2:
- tatami_activo: controla si el tatami acepta eventos
- nombre_categoria: nombre personalizable de la categoría activa
- Broadcast inicial ya incluye _categoria + _tatami_activo + _nombre_categoria
- aprobar_oro: Juez Central confirma ganador de Punto de Oro
- activar_competidor / cerrar_puntuacion: control de turno en Figuras
- Validaciones de asignación de roles
"""

import copy
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from flask import request
from flask_socketio import ConnectionRefusedError, Namespace, emit, join_room, leave_room
from flask_jwt_extended import decode_token

from ..engine.combate_engine import (
    ACCIONES_BLOQUEADAS_DURANTE_ALERTA,
    ACCIONES_BLOQUEADAS_TRAS_GANADOR,
    estado_inicial,
    aplicar_evento,
    guardar_combate_snapshot,
    _agregar_log,
)
from ..engine.figuras_engine import (
    estado_inicial_figuras,
    aplicar_evento_figuras,
    guardar_figuras_snapshot,
)
from ..extensions import db, socketio
from ..models.combate import Combate, EventoCombate
from ..models.tatami import SesionTatami
from ..models.asignacion import AccesoTatami, AsignacionJuez
from ..timeutil import iso_utc


# ══════════════════════════════════════════
#  ESTADO IN-MEMORY POR TATAMI
# ══════════════════════════════════════════
tatami_states = {}
MAX_EVENTOS_VISTOS = 500

_lock = threading.Lock()

# ── Persistencia a disco: el estado sobrevive reinicios del backend ──
_SNAPSHOT_PATH = Path(__file__).resolve().parents[2] / "instance" / "tatami_states.json"
_snapshots_cargados = False


def _serializar_ts(ts):
    """Parte JSON-serializable del estado de un tatami."""
    return {
        "estado": ts.get("estado", {}),
        "categoria_activa": ts.get("categoria_activa", "combate"),
        "nombre_categoria": ts.get("nombre_categoria", "Figuras"),
        "tatami_activo": ts.get("tatami_activo", False),
        "secuencia": ts.get("secuencia", 0),
        "sesion_id": ts.get("sesion_id"),
        "jueces_meta": ts.get("jueces_meta", {}),
        "tatami_numero": ts.get("tatami_numero"),
        "campeonato_nombre": ts.get("campeonato_nombre"),
        "campeonato_id": ts.get("campeonato_id"),
        "combate_llave": ts.get("combate_llave"),
        "grupo_figuras": ts.get("grupo_figuras"),
        "mostrar_arbol": bool(ts.get("mostrar_arbol")),
        "llave_arbol": ts.get("llave_arbol"),
        "proximos_llave": ts.get("proximos_llave"),
        # Registros locales de jueces pendientes de que la mesa los resuelva
        "propuestas_local": ts.get("propuestas_local", {}),
    }


def _persistir_estados():
    """Escribe los estados de todos los tatamis a disco (reemplazo atómico)."""
    try:
        data = {tid: _serializar_ts(ts) for tid, ts in tatami_states.items()}
        _SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = _SNAPSHOT_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, _SNAPSHOT_PATH)
    except Exception as e:
        print(f"  [WARN] No se pudo persistir estado de tatamis: {e}")


def _cargar_estados():
    """Restaura los estados desde disco al primer acceso tras un reinicio."""
    global _snapshots_cargados
    if _snapshots_cargados:
        return
    _snapshots_cargados = True
    try:
        if not _SNAPSHOT_PATH.exists():
            return
        data = json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        for tid, guardado in data.items():
            estado = guardado.get("estado") or estado_inicial()
            # El cronómetro vuelve pausado: el Juez Central decide reanudar.
            if "activo" in estado:
                estado["activo"] = False
            tatami_states[tid] = {
                "estado": estado,
                "categoria_activa": guardado.get("categoria_activa", "combate"),
                "nombre_categoria": guardado.get("nombre_categoria", "Figuras"),
                "tatami_activo": guardado.get("tatami_activo", False),
                "eventos_vistos": set(),
                "secuencia": guardado.get("secuencia", 0),
                "crono_thread": None,
                "crono_activo": False,
                "sesion_id": guardado.get("sesion_id"),
                "jueces_meta": guardado.get("jueces_meta", {}),
                "roles_activos": {},
                "tatami_numero": guardado.get("tatami_numero"),
                "campeonato_nombre": guardado.get("campeonato_nombre"),
                "campeonato_id": guardado.get("campeonato_id"),
                "combate_llave": guardado.get("combate_llave"),
                "grupo_figuras": guardado.get("grupo_figuras"),
                "mostrar_arbol": bool(guardado.get("mostrar_arbol")),
                "llave_arbol": guardado.get("llave_arbol"),
                "proximos_llave": guardado.get("proximos_llave"),
                "propuestas_local": guardado.get("propuestas_local", {}),
            }
        if data:
            print(f"  [OK] Estado de {len(data)} tatami(s) restaurado tras reinicio")
    except Exception as e:
        print(f"  [WARN] No se pudo restaurar estado de tatamis: {e}")

# Acciones permitidas cuando tatami ESTÁ DESACTIVADO.
# Se puede CONFIGURAR el combate/figuras con el tatami aún desactivado (nombres,
# jueces, ronda, duración, competidores, cargar de la cola) para dejarlo listo y
# luego activar. Lo único que NO se permite sin activar es iniciar el cronómetro
# y puntuar.
ACCIONES_SIN_ACTIVACION = {
    "activar_tatami",
    "desactivar_tatami",
    "cambiar_categoria",
    "cambiar_nombre_categoria",
    "cambiar_descripcion",
    "nombres",
    "set_num_jueces",
    "set_nombre_juez",
    "ronda",
    "crono_reset",
    "agregar_competidor",
    "eliminar_competidor",
    "reset",
    "reset_figuras",
    "activar_combate_llave",
    "soltar_combate_llave",
    "activar_grupo_figuras",
    "soltar_grupo_figuras",
    "mostrar_arbol",
    # El registro local llega apenas el juez reconecta, esté o no activo el
    # tatami; la mesa lo resuelve cuando pueda.
    "proponer_registro_local",
    "resolver_registro_local",
}

ACCIONES_DURANTE_GANADOR_PENDIENTE = {"cerrar_ganador", "cerrar_alerta12"}

# Acciones que SÍ requieren los nombres de ambos competidores: puntuar, iniciar
# el cronómetro y decidir el resultado. La configuración (jueces, ronda,
# duración, reset) NO los requiere, para poder prepararla antes de los nombres.
ACCIONES_REQUIEREN_COMPETIDORES = {
    "punto_juez",
    "deshacer_juez",
    "especial",
    "deshacer_arbitro",
    "kyonggo",
    "gamjeum",
    "crono_start",
    "aprobar_oro",
    "rechazar_oro",
    "declarar_ganador",
    "descalificar",
}

ACCIONES_FIGURAS_SIN_NOMBRE_CATEGORIA = {
    "activar_tatami",
    "desactivar_tatami",
    "cambiar_categoria",
    "cambiar_nombre_categoria",
    "cambiar_descripcion",
    # Activar un grupo de la cola fija un nombre de categoría válido por sí mismo.
    "activar_grupo_figuras",
}

ACCIONES_SOLO_ARBITRO = {
    "activar_tatami",
    "desactivar_tatami",
    "cambiar_categoria",
    "cambiar_nombre_categoria",
    "nuevo_combate",
    "reset",
    "reset_figuras",
    "crono_start",
    "crono_pause",
    "crono_reset",
    "ronda",
    "set_num_jueces",
    "especial",
    "deshacer_arbitro",
    "kyonggo",
    "gamjeum",
    "aprobar_oro",
    "rechazar_oro",
    "declarar_ganador",
    "descalificar",
    "cerrar_ganador",
    "cerrar_alerta12",
    "agregar_competidor",
    "eliminar_competidor",
    "activar_competidor",
    "cerrar_puntuacion",
    "reevaluar_empate",
    "finalizar",
    "cambiar_descripcion",
    "activar_combate_llave",
    "soltar_combate_llave",
    "activar_grupo_figuras",
    "soltar_grupo_figuras",
    "mostrar_arbol",
    "resolver_registro_local",
    "anular_entrada",
}

CATEGORIA_NOMBRE_MAX = 40
CATEGORIA_NOMBRE_RE = re.compile(r"^[A-Za-zÁÉÍÓÚÜÑáéíóúüñ ]+$")

# Máximo 4 jueces de esquina por tatami (más el Juez Central)
ROL_LABELS = {
    "arbitro": "Juez Central",
    "j1": "Juez 1",
    "j2": "Juez 2",
    "j3": "Juez 3",
    "j4": "Juez 4",
}


def _info_tatami(tatami_id):
    """Número visible, nombre e id del campeonato del tatami."""
    try:
        from ..models.tatami import Tatami as TatamiModel
        from ..models.campeonato import Campeonato as CampeonatoModel

        tatami = TatamiModel.query.get(int(tatami_id))
        if not tatami:
            return None, None, None
        camp = CampeonatoModel.query.get(tatami.campeonato_id) if tatami.campeonato_id else None
        return tatami.numero, (camp.nombre if camp else None), tatami.campeonato_id
    except Exception:
        return None, None, None


def _num_combate_hoy(tatami_id):
    """
    Número de combate del día para este tatami: cuántos combates (no figuras)
    se han guardado HOY (día local) + 1. Sirve para coordinar con la mesa y el
    llamado por altavoz ("Combate #12").
    """
    try:
        from datetime import timedelta
        # Medianoche local de hoy → UTC naive (como se guarda created_at)
        hoy_local = datetime.now().astimezone().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        hoy_utc = hoy_local.astimezone(timezone.utc).replace(tzinfo=None)
        sesion_ids = [
            s.id for s in SesionTatami.query.filter_by(tatami_id=int(tatami_id)).all()
        ]
        if not sesion_ids:
            return 1
        n = (
            Combate.query
            .filter(Combate.sesion_tatami_id.in_(sesion_ids))
            .filter(Combate.created_at >= hoy_utc)
            .filter(Combate.ronda_final != "figuras")
            .count()
        )
        return n + 1
    except Exception:
        return None


def _get_tatami_state(tatami_id):
    """Obtiene o crea el estado de un tatami."""
    _cargar_estados()
    tid = str(tatami_id)
    if tid not in tatami_states:
        numero, camp_nombre, camp_id = _info_tatami(tatami_id)
        tatami_states[tid] = {
            "estado": estado_inicial(),
            "categoria_activa": "combate",
            "nombre_categoria": "Figuras",   # nombre custom solo aplica a figuras
            "tatami_activo": False,          # inicia desactivado
            "eventos_vistos": set(),
            "secuencia": 0,
            "crono_thread": None,
            "crono_activo": False,
            "sesion_id": None,
            "jueces_meta": {},
            "roles_activos": {},
            "tatami_numero": numero,
            "campeonato_nombre": camp_nombre,
            "campeonato_id": camp_id,
            "propuestas_local": {},
        }
    ts = tatami_states[tid]
    # Estados restaurados de versiones previas pueden no tener el número
    if ts.get("tatami_numero") is None or ts.get("campeonato_id") is None:
        numero, camp_nombre, camp_id = _info_tatami(tatami_id)
        ts["tatami_numero"] = numero
        ts["campeonato_nombre"] = camp_nombre
        ts["campeonato_id"] = camp_id
    # Número de combate del día (se calcula una vez y se actualiza al guardar)
    if ts.get("num_combate") is None:
        ts["num_combate"] = _num_combate_hoy(tatami_id)
    return ts


def _room_name(tatami_id):
    return f"tatami_{tatami_id}"


def _build_estado_broadcast(ts):
    """Agrega metadatos al estado antes de broadcast."""
    estado_copy = copy.deepcopy(ts["estado"])
    estado_copy["_categoria"] = ts.get("categoria_activa", "combate")
    estado_copy["_tatami_activo"] = ts.get("tatami_activo", False)
    estado_copy["_nombre_categoria"] = ts.get("nombre_categoria", "Figuras")
    estado_copy["_tatami_numero"] = ts.get("tatami_numero")
    estado_copy["_campeonato_nombre"] = ts.get("campeonato_nombre")
    estado_copy["_campeonato_id"] = ts.get("campeonato_id")
    estado_copy["_combate_llave"] = ts.get("combate_llave")
    estado_copy["_grupo_figuras"] = ts.get("grupo_figuras")
    # Árbol de la llave para la pantalla pública. La estructura completa
    # solo viaja cuando está visible (los ticks del cronómetro no la cargan),
    # pero _hay_arbol siempre indica si existe para el botón del Juez Central.
    estado_copy["_mostrar_arbol"] = bool(ts.get("mostrar_arbol"))
    estado_copy["_hay_arbol"] = bool(ts.get("llave_arbol"))
    estado_copy["_llave_arbol"] = ts.get("llave_arbol") if ts.get("mostrar_arbol") else None
    # Número de combate del día (coordinación con la mesa / altavoz)
    estado_copy["_num_combate"] = ts.get("num_combate")
    # Próximos combates de la llave activa (pantalla pública)
    estado_copy["_proximos_llave"] = ts.get("proximos_llave") or []
    # Jueces conectados en este momento: {rol: nombre} (panel de la mesa)
    estado_copy["_roles_conectados"] = {
        rol: (info.get("nombre") or None)
        for rol, info in (ts.get("roles_activos") or {}).items()
    }
    # Registros locales de jueces esperando resolución del JC
    estado_copy["_propuestas_local"] = ts.get("propuestas_local") or {}
    return estado_copy


def _rol_label(rol):
    return ROL_LABELS.get(rol, rol or "-")


def _proximos_de_llave(estructura, excluir=None, limite=3):
    """
    Próximos combates jugables de una llave (para la pantalla pública):
    [{ronda_nombre, comp1, comp2}], excluyendo el partido en curso.
    """
    from ..api.llaves import partidos_jugables, etiqueta_ronda

    total = len((estructura or {}).get("rondas", []))
    proximos = []
    for r, i, p in partidos_jugables(estructura or {}):
        if excluir is not None and (r, i) == tuple(excluir):
            continue
        proximos.append({
            "ronda_nombre": etiqueta_ronda(r, total),
            "comp1": (p.get("comp1") or {}).get("nombre", "-"),
            "comp2": (p.get("comp2") or {}).get("nombre", "-"),
        })
        if len(proximos) >= limite:
            break
    return proximos


def roles_ocupados_para_tatami(tatami_id):
    """Roles actualmente conectados en un tatami."""
    tid = str(tatami_id)
    with _lock:
        ts = tatami_states.get(tid)
        if not ts:
            return set()
        return set(ts.get("roles_activos", {}).keys())


def _pareja_llave_coincide(ts):
    """
    El marcador sigue mostrando a los DOS competidores del partido de llave
    enganchado. Si no, ese marcador ya no representa ese partido y su
    resultado no puede avanzar en el cuadro.
    Sin llave enganchada responde True (nada que verificar).
    """
    info = ts.get("combate_llave")
    if not info:
        return True
    estado = ts.get("estado") or {}

    def _n(valor):
        return str(valor or "").strip().casefold()

    return (
        _n(estado.get("nombreHong")) == _n((info.get("comp1") or {}).get("nombre"))
        and _n(estado.get("nombreChung")) == _n((info.get("comp2") or {}).get("nombre"))
    )


def _competidores_de_llave_a_figuras(estado, comps):
    """Carga en el motor de figuras los competidores de una llave.

    El enlace con la ficha (`competidor_uid`, F3 de PLAN-CAMPEONATOS) se pone
    AQUÍ, desde el servidor, y a propósito no viaja dentro del evento: el motor
    no lo lee de `ev`, así que un cliente que mande `agregar_competidor` no
    puede colgarle un resultado a la ficha de otra persona. Desde aquí llega
    solo al ranking, que copia el competidor entero.
    """
    for c in comps:
        antes = len(estado["competidores"])
        aplicar_evento_figuras(estado, {
            "accion": "agregar_competidor",
            "nombre": c.get("nombre"),
            "club": c.get("club", ""),
            # Categoría especial marcada en el competidor: el motor de
            # figuras le da 1er puesto sin afectar el ranking normal.
            "especial": bool(c.get("especial")),
        })
        # Solo si el motor lo AÑADIÓ (un nombre vacío o el tope de 50 lo
        # descartan): si no, el uid iría a parar al competidor anterior.
        if c.get("competidor_uid") and len(estado["competidores"]) > antes:
            estado["competidores"][-1]["competidor_uid"] = c["competidor_uid"]
    return estado


def _competidores_con_nombre(estado):
    hong = (estado.get("nombreHong") or "").strip()
    chung = (estado.get("nombreChung") or "").strip()
    return bool(hong and chung and hong != "Hong" and chung != "Chung")


def _normalizar_nombre_categoria(nombre):
    raw = str(nombre or "")
    limpio = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ ]", "", raw)
    # Colapsar espacios y unificar en MAYÚSCULAS para que "Defensa" y
    # "defensa" no aparezcan como categorías distintas en el registro.
    limpio = re.sub(r"\s+", " ", limpio).strip().upper()
    return limpio[:CATEGORIA_NOMBRE_MAX]


def _nombre_categoria_valido(nombre):
    valor = str(nombre or "").strip()
    return bool(valor and CATEGORIA_NOMBRE_RE.fullmatch(valor))


def _meta_desde_asignacion(asig):
    usuario = asig.usuario if asig else None
    return {
        "usuario_id": usuario.id if usuario else None,
        "nombre": (asig.nombre_display or usuario.nombre) if usuario else None,
        "email": usuario.email if usuario else "",
        "rol_tatami": asig.rol_tatami if asig else None,
        "asignacion": _rol_label(asig.rol_tatami) if asig else None,
        "origen": "asignacion",
        "asignado_at": iso_utc(asig.asignado_at) if asig else None,
        "asignado_por": (
            {
                "id": asig.asignado_por.id,
                "nombre": asig.asignado_por.nombre,
                "email": asig.asignado_por.email,
            }
            if asig and asig.asignado_por else None
        ),
    }


def _meta_desde_conexion(rol, user_id=None, nombre=None, email=None, origen="directo"):
    return {
        "usuario_id": int(user_id) if user_id else None,
        "nombre": nombre or _rol_label(rol),
        "email": email or "",
        "rol_tatami": rol,
        "asignacion": _rol_label(rol),
        "origen": origen,
        "asignado_at": None,
        "asignado_por": None,
    }


class CombateNamespace(Namespace):
    """Namespace Socket.IO para combates en tiempo real."""

    def on_connect(self, auth=None):
        tatami_id = request.args.get("tatami_id")
        rol = request.args.get("rol", "pantalla")
        # El token viaja en el payload `auth` de Socket.IO (no queda en logs
        # de URLs). Se acepta query string como compatibilidad hacia atrás.
        token = None
        if isinstance(auth, dict):
            token = auth.get("token")
        token = token or request.args.get("token")

        # Mantenimiento: nadie entra al tatami mientras se sube una versión
        # nueva, salvo el superadmin (ver app/mantenimiento.py).
        from ..mantenimiento import socket_permitido

        if not socket_permitido(token):
            raise ConnectionRefusedError(
                "El sistema está en mantenimiento. Vuelve a intentarlo en unos minutos."
            )

        if not tatami_id:
            raise ConnectionRefusedError("tatami_id requerido")

        if rol not in {"pantalla", *ROL_LABELS.keys()}:
            raise ConnectionRefusedError("Rol de juez inválido")

        # Autenticación opcional
        user_id = None
        user_nombre = None
        user_email = None
        if token:
            try:
                decoded = decode_token(token)
                user_id = decoded.get("sub")
                user_nombre = decoded.get("nombre", "")
                user_email = decoded.get("email", "")
            except Exception:
                pass

        sid_anterior = None
        with _lock:
            ts = _get_tatami_state(tatami_id)
            if rol != "pantalla":
                activo = ts.setdefault("roles_activos", {}).get(rol)
                if activo and activo.get("sid") != request.sid:
                    # TAKEOVER: una recarga de página o un cambio de dispositivo
                    # NO puede dejar al juez bloqueado fuera del tatami (el sid
                    # viejo tarda en soltarse por ping-timeout). La conexión
                    # nueva reemplaza a la anterior; a la vieja se le avisa y
                    # se desconecta (si aún existe).
                    sid_anterior = activo.get("sid")
                ts["roles_activos"][rol] = {
                    "sid": request.sid,
                    "usuario_id": int(user_id) if user_id else None,
                    "nombre": user_nombre,
                    "email": user_email,
                }

        if sid_anterior:
            try:
                socketio.emit(
                    "sesion_reemplazada",
                    {
                        "message": f"{_rol_label(rol)} se conectó desde otra "
                                   "pantalla o dispositivo. Esta sesión quedó inactiva.",
                    },
                    namespace="/combate",
                    to=sid_anterior,
                )
                socketio.server.disconnect(sid_anterior, namespace="/combate")
            except Exception:
                pass
            print(f"  [CONN] [{_room_name(tatami_id)}] {rol} reconectado — "
                  f"sesión anterior reemplazada (sid viejo={sid_anterior})")

        # Registrar acceso
        try:
            acceso = AccesoTatami(
                tatami_id=int(tatami_id),
                usuario_id=int(user_id) if user_id else None,
                nombre_visitante=user_nombre or request.args.get("nombre", "Anónimo"),
                rol_seleccionado=rol,
                ip_address=request.remote_addr,
            )
            db.session.add(acceso)
            db.session.commit()
        except Exception:
            db.session.rollback()

        join_room(_room_name(tatami_id))

        # Enviar estado completo CON metadatos desde el primer momento.
        # La meta del juez se arma FUERA del lock (toca la BD); la mutación
        # de jueces_meta y el snapshot del estado, dentro (otro hilo puede
        # estar mutándolo).
        meta_rol = None
        try:
            asignacion = (
                AsignacionJuez.query.filter_by(
                    tatami_id=int(tatami_id), usuario_id=int(user_id)
                ).first()
                if user_id else None
            )
            if asignacion and asignacion.rol_tatami == rol:
                meta_rol = _meta_desde_asignacion(asignacion)
        except Exception:
            meta_rol = None
        if meta_rol is None and rol != "pantalla":
            meta_rol = _meta_desde_conexion(
                rol, user_id=user_id, nombre=user_nombre, email=user_email, origen="directo"
            )
        with _lock:
            if meta_rol is not None:
                ts["jueces_meta"][rol] = meta_rol
            datos = _build_estado_broadcast(ts)
        emit("estado", {"datos": datos})
        # Avisar al resto del tatami que este rol se conectó (el panel de
        # conexiones del Juez Central se actualiza al instante).
        if rol != "pantalla":
            socketio.emit(
                "estado", {"datos": datos}, namespace="/combate",
                to=_room_name(tatami_id),
            )

        print(f"  [CONN] [{_room_name(tatami_id)}] {rol} conectado (sid={request.sid})")

    def on_disconnect(self):
        tatami_id = request.args.get("tatami_id")
        rol = request.args.get("rol", "pantalla")
        if not tatami_id or rol == "pantalla":
            return
        datos = None
        with _lock:
            ts = tatami_states.get(str(tatami_id))
            if not ts:
                return
            activo = ts.get("roles_activos", {}).get(rol)
            if activo and activo.get("sid") == request.sid:
                ts["roles_activos"].pop(rol, None)
                datos = _build_estado_broadcast(ts)
        # Avisar la desconexión al tatami (fuera del lock)
        if datos is not None:
            socketio.emit(
                "estado", {"datos": datos}, namespace="/combate",
                to=_room_name(tatami_id),
            )

    def on_pedir(self, data=None):
        """Cliente solicita estado completo (reconexión)."""
        tatami_id = request.args.get("tatami_id")
        if not tatami_id:
            return
        # Snapshot bajo lock: copiar el estado mientras otro hilo lo muta
        # puede lanzar excepción y dejar al cliente sin respuesta.
        with _lock:
            ts = _get_tatami_state(tatami_id)
            datos = _build_estado_broadcast(ts)
        emit("estado", {"datos": datos})

    def on_evento(self, data):
        """
        Recibe un evento delta del cliente.
        data: { evId, evento: { accion, ...datos } }
        """
        tatami_id = request.args.get("tatami_id")
        if not tatami_id:
            return
        rol = request.args.get("rol", "pantalla")

        ev = data.get("evento", {})
        ev_id = data.get("evId")

        with _lock:
            ts = _get_tatami_state(tatami_id)
            room = _room_name(tatami_id)

            # Deduplicación
            if ev_id and ev_id in ts["eventos_vistos"]:
                emit("ack", {"evId": ev_id})
                return
            if ev_id:
                ts["eventos_vistos"].add(ev_id)
                if len(ts["eventos_vistos"]) > MAX_EVENTOS_VISTOS:
                    ts["eventos_vistos"].pop()

            accion = ev.get("accion")

            if accion in ACCIONES_SOLO_ARBITRO and rol != "arbitro":
                if ev_id:
                    emit("ack", {"evId": ev_id})
                emit("accion_rechazada", {
                    "message": "Esta acción requiere Juez Central."
                })
                return

            # ── Bloqueo si tatami desactivado ──────────────────────────────
            if not ts.get("tatami_activo", False) and accion not in ACCIONES_SIN_ACTIVACION:
                if ev_id:
                    emit("ack", {"evId": ev_id})
                return  # Silently ignore

            if ts["estado"].get("ganadorPendienteCierre") and accion not in ACCIONES_DURANTE_GANADOR_PENDIENTE:
                if ev_id:
                    emit("ack", {"evId": ev_id})
                return

            # Combate cerrado: con ganador declarado solo procede guardar
            # (Nuevo Combate) o descartar (Reset).
            if (
                ts.get("categoria_activa", "combate") == "combate"
                and ts["estado"].get("ganadorManualColor")
                and accion in ACCIONES_BLOQUEADAS_TRAS_GANADOR
            ):
                if ev_id:
                    emit("ack", {"evId": ev_id})
                emit("accion_rechazada", {
                    "message": "El combate ya tiene ganador. Usa NUEVO COMBATE "
                               "para guardarlo o RESET para descartarlo."
                })
                return

            # Combate en pausa mientras la alerta de superioridad esté abierta
            if (
                ts.get("categoria_activa", "combate") == "combate"
                and ts["estado"].get("alerta12Data")
                and accion in ACCIONES_BLOQUEADAS_DURANTE_ALERTA
            ):
                if ev_id:
                    emit("ack", {"evId": ev_id})
                emit("accion_rechazada", {
                    "message": "Combate en pausa por la alerta de superioridad. "
                               "El Juez Central debe cerrarla para continuar."
                })
                return

            if accion == "cerrar_ganador" and rol != "arbitro":
                if ev_id:
                    emit("ack", {"evId": ev_id})
                return

            if (
                ts.get("categoria_activa", "combate") == "combate"
                and accion in ACCIONES_REQUIEREN_COMPETIDORES
                and not _competidores_con_nombre(ts["estado"])
            ):
                if ev_id:
                    emit("ack", {"evId": ev_id})
                emit("accion_rechazada", {
                    "message": "Ingresa los nombres de ambos competidores antes de continuar."
                })
                return

            if (
                ts.get("categoria_activa") == "figuras"
                and accion not in ACCIONES_FIGURAS_SIN_NOMBRE_CATEGORIA
                and not _nombre_categoria_valido(ts["estado"].get("nombre_categoria"))
            ):
                if ev_id:
                    emit("ack", {"evId": ev_id})
                emit("accion_rechazada", {
                    "message": "Ingresa un nombre de categoría válido usando solo letras y espacios."
                })
                return

            # ── Activar / Desactivar tatami ────────────────────────────────
            if accion == "activar_tatami":
                ts["tatami_activo"] = True
                _agregar_log(ts["estado"], "[ON] Tatami activado", "arb")
                if ev_id:
                    emit("ack", {"evId": ev_id})
                self._broadcast_estado(room, ts)
                return

            if accion == "desactivar_tatami":
                ts["tatami_activo"] = False
                ts["crono_activo"] = False  # Detener crono también
                _agregar_log(ts["estado"], "[OFF] Tatami desactivado", "arb")
                if ev_id:
                    emit("ack", {"evId": ev_id})
                self._broadcast_estado(room, ts)
                return

            # ── Cambio de nombre de categoría ─────────────────────────────
            if accion == "cambiar_nombre_categoria":
                nombre = _normalizar_nombre_categoria(ev.get("nombre", ""))
                ts["nombre_categoria"] = nombre
                if ts.get("categoria_activa") == "figuras" and "nombre_categoria" in ts["estado"]:
                    ts["estado"]["nombre_categoria"] = nombre
                if ev_id:
                    emit("ack", {"evId": ev_id})
                self._broadcast_estado(room, ts)
                return

            # ── Activar / soltar combate de eliminación (llave) ────────────
            if accion == "activar_combate_llave":
                error = self._activar_combate_llave(tatami_id, ts, ev)
                if ev_id:
                    emit("ack", {"evId": ev_id})
                if error:
                    emit("accion_rechazada", {"message": error})
                    return
                self._broadcast_estado(room, ts)
                return

            # ── Activar grupo de figuras (cola) ────────────────────────────
            if accion == "activar_grupo_figuras":
                error = self._activar_grupo_figuras(tatami_id, ts, ev)
                if ev_id:
                    emit("ack", {"evId": ev_id})
                if error:
                    emit("accion_rechazada", {"message": error})
                    return
                self._broadcast_estado(room, ts)
                return

            if accion == "soltar_combate_llave":
                if self._cerrar_combate_llave(ts):
                    _agregar_log(
                        ts["estado"],
                        "[LLAVE] Combate de eliminación liberado — marcador suelto, "
                        "la llave vuelve a pendiente",
                        "arb",
                    )
                if ev_id:
                    emit("ack", {"evId": ev_id})
                self._broadcast_estado(room, ts)
                return

            # ── Soltar grupo de figuras: lo desvincula y vuelve a 'pendiente' ─
            if accion == "soltar_grupo_figuras":
                if ts.get("grupo_figuras"):
                    self._cerrar_grupo_figuras(ts, terminada=False)
                    _agregar_log(
                        ts["estado"],
                        "[FIGURAS] Grupo liberado — vuelve a la cola como pendiente",
                        "arb",
                    )
                if ev_id:
                    emit("ack", {"evId": ev_id})
                self._broadcast_estado(room, ts)
                return

            # ── Mostrar árbol / puntuación en la pantalla pública ──────────
            if accion == "mostrar_arbol":
                if ts.get("llave_arbol"):
                    ts["mostrar_arbol"] = bool(ev.get("mostrar", True))
                if ev_id:
                    emit("ack", {"evId": ev_id})
                self._broadcast_estado(room, ts)
                return

            # ── Nuevo combate / nueva categoría ────────────────────────────
            if accion == "nuevo_combate":
                categoria = ts.get("categoria_activa", "combate")
                llave_info = ts.get("combate_llave") if categoria == "combate" else None

                # Última defensa: si el marcador ya no muestra a los dos
                # competidores del partido enganchado, guardar aquí haría
                # avanzar en el cuadro a alguien que nunca disputó ese combate.
                # Se guarda como combate suelto y la llave se libera.
                if llave_info and not _pareja_llave_coincide(ts):
                    self._cerrar_combate_llave(ts)
                    _agregar_log(
                        ts["estado"],
                        "[LLAVE] El marcador ya no corresponde a "
                        f"{llave_info['comp1']['nombre']} vs {llave_info['comp2']['nombre']}: "
                        "se guarda como combate suelto y la llave vuelve a pendiente",
                        "arb",
                    )
                    llave_info = None

                # Combate de eliminación: debe haber un ganador definido
                ganador_color = None
                if llave_info:
                    if not ts["estado"].get("historial"):
                        if ev_id:
                            emit("ack", {"evId": ev_id})
                        emit("accion_rechazada", {
                            "message": "No hay puntos registrados en este combate de eliminación. "
                                       "Usa 'Soltar combate' si no se va a disputar."
                        })
                        return
                    snap = guardar_combate_snapshot(ts["estado"])
                    ganador_color = snap.get("ganador_manual") or (
                        "hong" if snap["marcador_hong"] > snap["marcador_chung"]
                        else "chung" if snap["marcador_chung"] > snap["marcador_hong"]
                        else "empate"
                    )
                    if ganador_color == "empate":
                        if ev_id:
                            emit("ack", {"evId": ev_id})
                        emit("accion_rechazada", {
                            "message": "En un combate de eliminación debe haber un ganador. "
                                       "Usa Punto de Oro o la decisión del Juez Central para desempatar."
                        })
                        return

                self._guardar_combate_actual(tatami_id, ts, llave_info=llave_info)
                if categoria == "figuras":
                    # Si venía de un grupo de la cola, queda 'terminada' al guardar.
                    self._cerrar_grupo_figuras(ts, terminada=True)
                    nombre_cat = ts.get("nombre_categoria", "Figuras")
                    nuevo = estado_inicial_figuras()
                    nuevo["nombre_categoria"] = nombre_cat
                    ts["estado"] = nuevo
                    _agregar_log(
                        ts["estado"],
                        f"[OK] {nombre_cat} guardada — Nueva categoría",
                        "arb",
                    )
                else:
                    seg_max = ts["estado"].get("segundosMax", 120)
                    num_j = ts["estado"].get("numJueces", 4)
                    nombres_j = copy.deepcopy(ts["estado"].get("nombresJueces", {}))
                    ts["estado"] = estado_inicial()
                    ts["estado"]["segundosMax"] = seg_max
                    ts["estado"]["segundos"] = seg_max
                    ts["estado"]["numJueces"] = num_j
                    ts["estado"]["nombresJueces"] = nombres_j
                    _agregar_log(ts["estado"], "[OK] Combate guardado — Nuevo combate", "arb")

                # El ganador avanza en la llave y se libera el tatami
                if llave_info and ganador_color in ("hong", "chung"):
                    self._registrar_resultado_llave(ts, llave_info, ganador_color)

                self._detener_crono(tatami_id)
                if ev_id:
                    emit("ack", {"evId": ev_id})
                self._broadcast_estado(room, ts)
                return

            # ── Callback ganador Punto de Oro ──────────────────────────────
            def ganador_cb(nombre, color, motivo="Punto de Oro"):
                payload = {
                    "tipo": "ganador-flash",
                    "nombre": nombre,
                    "color": color,
                    "motivo": motivo,
                }
                socketio.emit("ganador-flash", payload, namespace="/combate", to=room)
                self._detener_crono(tatami_id)

            def alerta_superioridad_cb(payload):
                socketio.emit("alerta12", payload, namespace="/combate", to=room)
                # El combate se pausa hasta que el JC cierre la alerta
                self._detener_crono(tatami_id)

            def derrota_cb(perdedor, razon):
                # Descalificación automática: modal de derrota en todos los
                # dispositivos del tatami (el ganador sale por ganador_cb).
                socketio.emit(
                    "derrota",
                    {"perdedor": perdedor, "razon": razon},
                    namespace="/combate",
                    to=room,
                )
                self._detener_crono(tatami_id)

            # ── Cambio de categoría ────────────────────────────────────────
            if accion == "cambiar_categoria":
                # Abandona el grupo de figuras en curso (vuelve a 'pendiente').
                self._cerrar_grupo_figuras(ts, terminada=False)
                # Y también el combate de eliminación: el marcador se reinicia
                # aquí, así que el partido enganchado deja de tener respaldo.
                self._cerrar_combate_llave(ts)
                nueva_cat = ev.get("categoria", "combate")
                ts["categoria_activa"] = nueva_cat
                if nueva_cat == "figuras":
                    nuevo = estado_inicial_figuras()
                    nuevo["nombre_categoria"] = ts.get("nombre_categoria", "Figuras")
                    ts["estado"] = nuevo
                else:
                    ts["estado"] = estado_inicial()
                self._detener_crono(tatami_id)
                if ev_id:
                    emit("ack", {"evId": ev_id})
                self._broadcast_estado(room, ts)
                return

            # ── Registro local de un juez (se envía solo al reconectar) ────
            if accion == "proponer_registro_local":
                if rol in ("j1", "j2", "j3", "j4"):
                    entradas = []
                    for e in (ev.get("entradas") or [])[:100]:
                        color = e.get("color")
                        try:
                            pts = float(e.get("pts", 0))
                        except (TypeError, ValueError):
                            continue
                        if color not in ("hong", "chung") or not (0 < pts <= 10):
                            continue
                        entradas.append({
                            "ts": e.get("ts"),
                            "etiqueta": str(e.get("etiqueta", ""))[:60],
                            "color": color,
                            "pts": int(pts) if pts == int(pts) else pts,
                        })
                    if entradas:
                        meta = ts.get("jueces_meta", {}).get(rol) or {}
                        ts.setdefault("propuestas_local", {})[rol] = {
                            "nombre": meta.get("nombre") or _rol_label(rol),
                            "entradas": entradas,
                            "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
                        }
                        _agregar_log(
                            ts["estado"],
                            f"[MESA] {_rol_label(rol)} envió su registro local "
                            f"({len(entradas)} anotación(es)) — pendiente de la mesa",
                            "arb",
                        )
                if ev_id:
                    emit("ack", {"evId": ev_id})
                self._broadcast_estado(room, ts)
                return

            # ── La mesa (JC) aplica o descarta un registro local ───────────
            if accion == "resolver_registro_local":
                rol_obj = ev.get("rol")
                propuesta = ts.get("propuestas_local", {}).get(rol_obj)
                if not propuesta:
                    if ev_id:
                        emit("ack", {"evId": ev_id})
                    return
                aplicar = bool(ev.get("aplicar"))
                estado = ts["estado"]
                if aplicar and (
                    ts.get("categoria_activa", "combate") != "combate"
                    or estado.get("ganadorManualColor")
                    or estado.get("alerta12Data")
                    or estado.get("oroPendienteAprobacion")
                ):
                    if ev_id:
                        emit("ack", {"evId": ev_id})
                    emit("accion_rechazada", {
                        "message": "No se puede aplicar ahora: el combate está "
                                   "cerrado, en alerta o no es la categoría "
                                   "Combate. Resuélvelo y vuelve a intentar."
                    })
                    return
                ts["propuestas_local"].pop(rol_obj, None)
                if aplicar:
                    aplicados = 0
                    for e in propuesta.get("entradas", []):
                        etiqueta = e.get("etiqueta") or "Registro local"
                        # La etiqueta viene como "+2 GIRO ...": quitar el
                        # prefijo para no duplicar los puntos en el log.
                        nombre_pt = re.sub(r"^\+[\d.]+\s*", "", etiqueta) or etiqueta
                        ev_punto = {
                            "accion": "punto_juez",
                            "juez": rol_obj,
                            "color": e.get("color"),
                            "pts": e.get("pts"),
                            "nombre": f"{nombre_pt} (registro local)",
                        }
                        self._inyectar_meta_juez(ts, ev_punto, rol_obj)
                        antes = len(estado["historial"])
                        aplicar_evento(
                            estado, ev_punto,
                            ganador_cb, alerta_superioridad_cb, derrota_cb,
                        )
                        if len(estado["historial"]) > antes:
                            aplicados += 1
                    _agregar_log(
                        estado,
                        f"[MESA] Registro local de {_rol_label(rol_obj)} "
                        f"APLICADO: {aplicados} punto(s) sumado(s)",
                        "arb",
                    )
                else:
                    _agregar_log(
                        estado,
                        f"[MESA] Registro local de {_rol_label(rol_obj)} "
                        "descartado por la mesa",
                        "arb",
                    )
                # El juez dueño del registro limpia su libreta al recibir esto
                socketio.emit(
                    "registro_local_resuelto",
                    {"rol": rol_obj, "aplicado": aplicar},
                    namespace="/combate", to=room,
                )
                if ev_id:
                    emit("ack", {"evId": ev_id})
                self._broadcast_estado(room, ts)
                return

            # ── Aplicar evento al estado ───────────────────────────────────
            categoria = ts.get("categoria_activa", "combate")
            self._inyectar_meta_juez(ts, ev, rol)
            if categoria == "figuras":
                aplicar_evento_figuras(ts["estado"], ev)
                # Reset de figuras abandona el grupo de la cola (vuelve a pendiente).
                if accion in ("reset_figuras", "reset"):
                    self._cerrar_grupo_figuras(ts, terminada=False)
            else:
                aplicar_evento(ts["estado"], ev, ganador_cb, alerta_superioridad_cb, derrota_cb)
                # El reset devuelve el marcador a cero y borra los nombres: el
                # partido de la llave queda sin respaldo y debe desengancharse,
                # o el SIGUIENTE combate que se guarde avanzaría ese partido.
                if accion == "reset":
                    if self._cerrar_combate_llave(ts):
                        _agregar_log(
                            ts["estado"],
                            "[LLAVE] Combate de eliminación liberado por el reset — "
                            "la llave vuelve a pendiente",
                            "arb",
                        )
                # Cambiar los nombres a mano rompe el vínculo con el cuadro.
                elif accion == "nombres" and not _pareja_llave_coincide(ts):
                    if self._cerrar_combate_llave(ts):
                        _agregar_log(
                            ts["estado"],
                            "[LLAVE] El marcador cambió de competidores — llave "
                            "liberada, vuelve a pendiente",
                            "arb",
                        )

            # ── Manejar cronómetro ─────────────────────────────────────────
            if accion == "crono_start":
                # Al iniciar el combate, la pantalla pública pasa del árbol
                # de la llave al marcador automáticamente.
                ts["mostrar_arbol"] = False
                self._iniciar_crono(tatami_id)
            elif accion in ("crono_pause", "crono_reset", "reset", "declarar_ganador"):
                self._detener_crono(tatami_id)
            elif accion == "cerrar_alerta12" and ts["estado"].get("activo"):
                # El JC cerró la alerta con "reanudar": el crono vuelve a correr
                self._iniciar_crono(tatami_id)

            # Si Punto de Oro resuelto, detener crono
            if categoria == "combate" and ts["estado"].get("oroResuelto"):
                self._detener_crono(tatami_id)

            # ── ACK + Broadcast ────────────────────────────────────────────
            ts["secuencia"] += 1
            if ev_id:
                emit("ack", {"evId": ev_id})
            self._broadcast_estado(room, ts)

    def on_broadcast(self, data):
        """
        Eventos de broadcast puro (no modifican estado):
        alerta12, derrota, falta-flash, ganador-flash
        """
        tatami_id = request.args.get("tatami_id")
        if not tatami_id:
            return
        with _lock:
            ts = _get_tatami_state(tatami_id)
            activo = ts.get("tatami_activo", False)
        if not activo:
            return

        room = _room_name(tatami_id)
        tipo = data.get("tipo")
        if tipo in ("alerta12", "derrota", "falta-flash", "ganador-flash"):
            payload = data.get("data") if isinstance(data.get("data"), dict) else {
                k: v for k, v in data.items() if k != "tipo"
            }
            if tipo == "falta-flash" and "tipo" not in payload:
                payload["tipo"] = payload.get("tipoFalta", "adv")
            emit(tipo, payload, to=room)

    def on_pedir_combates(self, data=None):
        """Cliente solicita lista de combates guardados."""
        tatami_id = request.args.get("tatami_id")
        if not tatami_id:
            return
        try:
            sesiones = SesionTatami.query.filter_by(tatami_id=int(tatami_id)).all()
            sesion_ids = [s.id for s in sesiones]
            combates = []
            if sesion_ids:
                combates_db = (
                    Combate.query
                    .filter(Combate.sesion_tatami_id.in_(sesion_ids))
                    .order_by(Combate.created_at.desc())
                    .limit(50)
                    .all()
                )
                combates = [c.to_dict() for c in combates_db]
            emit("combates_actualizados", {"combates": combates})
        except Exception:
            emit("combates_actualizados", {"combates": []})

    # ══════════════════════════════════════════
    #  HELPERS INTERNOS
    # ══════════════════════════════════════════

    def _broadcast_estado(self, room, ts):
        """Envía estado con metadatos a todos los clientes del room."""
        estado_copy = _build_estado_broadcast(ts)
        emit("estado", {"datos": estado_copy}, to=room)
        emit("estado_confirmado", {"datos": estado_copy})
        # Cada cambio de estado por evento queda persistido en disco
        # (los ticks del cronómetro no pasan por aquí, no saturan I/O).
        _persistir_estados()

    def _inyectar_meta_juez(self, ts, ev, rol_conexion):
        accion = ev.get("accion")
        actor_rol = None
        if accion == "punto_juez":
            actor_rol = ev.get("juez")
        elif accion in ("puntuar", "confirmar_puntuacion"):
            actor_rol = ev.get("juez_id")
        elif accion in (
            "especial", "kyonggo", "gamjeum", "deshacer_arbitro",
            "aprobar_oro", "rechazar_oro", "declarar_ganador",
        ):
            actor_rol = "arbitro"

        actor_rol = actor_rol or rol_conexion
        if not actor_rol or actor_rol == "pantalla":
            return

        meta = ts.get("jueces_meta", {}).get(actor_rol) or _meta_desde_conexion(
            actor_rol, origen="directo"
        )
        ev["juez_nombre"] = meta.get("nombre")
        ev["juez_email"] = meta.get("email")
        ev["juez_asignacion"] = meta.get("asignacion") or _rol_label(actor_rol)
        ev["juez_rol"] = meta.get("rol_tatami") or actor_rol
        ev["juez_acceso"] = meta.get("origen") or "directo"

    def _activar_combate_llave(self, tatami_id, ts, ev):
        """
        Activa el siguiente combate de eliminación de una llave en este tatami:
        autocompleta los nombres (comp1=Hong/Rojo, comp2=Chung/Azul) y deja el
        cronómetro pausado, listo para comenzar.
        Retorna un mensaje de error, o None si todo salió bien.
        """
        from ..models.llave import Llave
        from ..api.llaves import siguiente_partido, etiqueta_ronda

        if ts.get("categoria_activa", "combate") != "combate":
            return "Cambia a la categoría Combate antes de activar un combate de eliminación."

        estado = ts["estado"]
        if estado.get("historial") or estado.get("segundos", 0) < estado.get("segundosMax", 120):
            return "Guarda o resetea el combate actual antes de activar uno de eliminación."

        try:
            llave = Llave.query.get(int(ev.get("llave_id", 0)))
        except (TypeError, ValueError):
            llave = None
        if not llave:
            return "Llave no encontrada."
        if llave.tatami_id != int(tatami_id):
            return "Esta llave está asignada a otro tatami."

        sig = siguiente_partido(llave.estructura or {})
        if sig is None:
            return "No quedan combates pendientes en esta llave."

        ronda_idx, partido_idx, partido = sig
        total_rondas = len((llave.estructura or {}).get("rondas", []))

        # Nuevo marcador con los nombres del cuadro (crono pausado)
        seg_max = estado.get("segundosMax", 120)
        num_j = estado.get("numJueces", 4)
        nombres_j = copy.deepcopy(estado.get("nombresJueces", {}))
        nuevo = estado_inicial()
        nuevo["segundosMax"] = seg_max
        nuevo["segundos"] = seg_max
        nuevo["numJueces"] = num_j
        nuevo["nombresJueces"] = nombres_j
        nuevo["nombreHong"] = partido["comp1"]["nombre"]
        nuevo["nombreChung"] = partido["comp2"]["nombre"]
        ts["estado"] = nuevo

        ronda_label = etiqueta_ronda(ronda_idx, total_rondas)
        ts["combate_llave"] = {
            "llave_id": llave.id,
            "nombre": llave.nombre,
            "ronda": ronda_idx,
            "partido": partido_idx,
            "ronda_nombre": ronda_label,
            "comp1": partido["comp1"],
            "comp2": partido["comp2"],
        }
        # Los que siguen después de este (para que se vayan preparando)
        ts["proximos_llave"] = _proximos_de_llave(
            llave.estructura, excluir=(ronda_idx, partido_idx)
        )
        # El público ve el árbol hasta que el combate comience (crono_start)
        ts["llave_arbol"] = {
            "llave_id": llave.id,
            "nombre": llave.nombre,
            "estructura": copy.deepcopy(llave.estructura),
        }
        ts["mostrar_arbol"] = True
        self._detener_crono(tatami_id)
        # La llave pasa a "activa" mientras se disputa en este tatami.
        if llave.estado_norm == "pendiente":
            llave.estado = "activa"
            db.session.commit()
        _agregar_log(
            ts["estado"],
            f"[LLAVE] {llave.nombre} · {ronda_label}: "
            f"{partido['comp1']['nombre']} (Rojo) vs {partido['comp2']['nombre']} (Azul)",
            "arb",
        )
        return None

    def _registrar_resultado_llave(self, ts, llave_info, ganador_color):
        """El ganador del combate avanza en la llave; libera el tatami."""
        from ..models.llave import Llave
        from ..api.llaves import registrar_resultado, partidos_jugables

        try:
            llave = Llave.query.get(llave_info["llave_id"])
            if llave:
                estructura = copy.deepcopy(llave.estructura)
                lado = 1 if ganador_color == "hong" else 2
                registrar_resultado(
                    estructura, llave_info["ronda"], llave_info["partido"], lado
                )
                llave.estructura = estructura
                pendientes = len(partidos_jugables(estructura))
                # Terminada solo cuando no queda nada por jugar (incluido el bronce).
                if estructura.get("campeon") and pendientes == 0:
                    llave.estado = "terminada"
                db.session.commit()

                # El público vuelve a ver el árbol actualizado tras el combate
                ts["llave_arbol"] = {
                    "llave_id": llave.id,
                    "nombre": llave.nombre,
                    "estructura": copy.deepcopy(estructura),
                }
                ts["mostrar_arbol"] = True
                ts["proximos_llave"] = _proximos_de_llave(estructura)

                gano_bronce = llave_info.get("ronda") == "bronce"
                campeon = estructura.get("campeon")
                if campeon and pendientes == 0:
                    _agregar_log(
                        ts["estado"],
                        f"[LLAVE] 🏆 {campeon['nombre']} CAMPEÓN — {llave_info['nombre']}",
                        "arb",
                    )
                elif gano_bronce:
                    tercero = (estructura.get("bronce") or {})
                    nombre3 = ""
                    if tercero.get("ganador") in (1, 2):
                        c3 = tercero["comp1"] if tercero["ganador"] == 1 else tercero["comp2"]
                        nombre3 = (c3 or {}).get("nombre", "")
                    _agregar_log(
                        ts["estado"],
                        f"[LLAVE] 🥉 {nombre3} 3er puesto — "
                        f"{pendientes} combate(s) pendiente(s) en {llave_info['nombre']}",
                        "arb",
                    )
                else:
                    ganador = llave_info["comp1"] if lado == 1 else llave_info["comp2"]
                    _agregar_log(
                        ts["estado"],
                        f"[LLAVE] {ganador['nombre']} avanza — "
                        f"{pendientes} combate(s) pendiente(s) en {llave_info['nombre']}",
                        "arb",
                    )
        except Exception as e:
            db.session.rollback()
            print(f"  [ERR] Error registrando resultado en la llave: {e}")
        finally:
            ts.pop("combate_llave", None)

    def _cerrar_combate_llave(self, ts):
        """
        Desengancha el combate de eliminación en curso SIN registrar resultado:
        limpia el árbol de la pantalla pública y devuelve la llave a
        'pendiente' para que no quede bloqueada como 'activa' (no se podría
        editar, combinar ni re-sortear). Espejo de `_cerrar_grupo_figuras`.
        Retorna True si había un combate enganchado.
        """
        from ..models.llave import Llave

        info = ts.pop("combate_llave", None)
        ts["mostrar_arbol"] = False
        ts.pop("llave_arbol", None)
        ts.pop("proximos_llave", None)
        if not info:
            return False
        try:
            llave = Llave.query.get(info["llave_id"])
            if llave and llave.tipo_norm == "combate" and llave.estado_norm == "activa":
                llave.estado = "pendiente"
                db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"  [ERR] Error liberando la llave de combate: {e}")
        return True

    def _activar_grupo_figuras(self, tatami_id, ts, ev):
        """
        Activa un grupo de figuras de la cola en este tatami: cambia la
        categoría a Figuras y carga TODOS los competidores de golpe (adiós a
        agregarlos a mano en vivo). Retorna un mensaje de error o None.
        """
        from ..models.llave import Llave

        try:
            llave = Llave.query.get(int(ev.get("llave_id", 0)))
        except (TypeError, ValueError):
            llave = None
        if not llave:
            return "Grupo de figuras no encontrado."
        if llave.tipo_norm != "figuras":
            return "Esa llave no es de figuras."
        if llave.tatami_id != int(tatami_id):
            return "Este grupo está asignado a otro tatami."
        if llave.estado_norm == "terminada":
            return "Este grupo ya fue calificado."

        # No pisar una categoría de figuras en curso con puntuaciones sin guardar.
        actual = ts.get("estado", {})
        if (
            ts.get("categoria_activa") == "figuras"
            and actual.get("competidores")
            and not actual.get("finalizado")
            and any(actual.get("puntuaciones", {}).values())
        ):
            return ("Termina o guarda la categoría de figuras actual antes de "
                    "activar otro grupo.")

        nombre_cat = _normalizar_nombre_categoria(llave.nombre)
        nuevo = estado_inicial_figuras()
        nuevo["nombre_categoria"] = nombre_cat
        nuevo["descripcion"] = llave.descripcion or ""
        comps = (llave.estructura or {}).get("competidores", [])
        _competidores_de_llave_a_figuras(nuevo, comps)

        ts["categoria_activa"] = "figuras"
        ts["nombre_categoria"] = nombre_cat
        ts["estado"] = nuevo
        ts["grupo_figuras"] = {"llave_id": llave.id, "nombre": llave.nombre}
        self._detener_crono(tatami_id)
        if llave.estado_norm == "pendiente":
            llave.estado = "activa"
            db.session.commit()
        _agregar_log(
            ts["estado"],
            f"[FIGURAS] {nombre_cat} — {len(comps)} competidor(es) cargado(s)",
            "arb",
        )
        return None

    def _cerrar_grupo_figuras(self, ts, terminada):
        """
        Cierra el vínculo con el grupo de figuras activo: si terminada=True la
        llave queda 'terminada'; si no (cambio de categoría, reset), vuelve a
        'pendiente' para no dejarla bloqueada como 'activa'.
        """
        from ..models.llave import Llave

        grupo = ts.pop("grupo_figuras", None)
        if not grupo:
            return
        try:
            llave = Llave.query.get(grupo["llave_id"])
            if llave and llave.tipo_norm == "figuras" and llave.estado_norm != "terminada":
                llave.estado = "terminada" if terminada else "pendiente"
                db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"  [ERR] Error cerrando grupo de figuras: {e}")

    def _obtener_sesion_categoria(self, tatami_id, slug):
        from ..models.categoria import Categoria

        cat = Categoria.query.filter_by(slug=slug).first()
        if not cat:
            return None, None

        sesion = SesionTatami.query.filter_by(
            tatami_id=int(tatami_id),
            categoria_id=cat.id,
            estado="en_curso",
        ).first()
        if not sesion:
            sesion = SesionTatami(
                tatami_id=int(tatami_id),
                categoria_id=cat.id,
                estado="en_curso",
                inicio=datetime.now(timezone.utc),
            )
            db.session.add(sesion)
            db.session.flush()
        return sesion, cat

    def _guardar_combate_actual(self, tatami_id, ts, llave_info=None):
        """Guarda el combate actual en la base de datos."""
        estado = ts["estado"]
        categoria = ts.get("categoria_activa", "combate")

        # Para figuras, usar guardar_figuras_snapshot
        if categoria == "figuras":
            if not estado.get("competidores"):
                return
            snapshot = guardar_figuras_snapshot(estado)
            ranking = snapshot.get("ranking") or []
            # El campeón del registro es el 1° del podio normal; los de
            # categoría especial tienen su propio primer puesto aparte.
            ganador = next(
                (r for r in ranking if not r.get("especial")),
                ranking[0] if ranking else None,
            )
            jueces_detalle = {
                "tipo": "figuras",
                "nombre_categoria": snapshot.get("nombre_categoria", "Figuras"),
                "descripcion": snapshot.get("descripcion", ""),
                "ranking": ranking,
                "competidores": snapshot.get("competidores", []),
                "criterios": snapshot.get("criterios", []),
                "puntuaciones": snapshot.get("puntuaciones", {}),
                "puntuaciones_confirmadas": snapshot.get("puntuaciones_confirmadas", {}),
                "desempates": snapshot.get("desempates", []),
                "puntuaciones_completas": snapshot.get("puntuaciones_completas", False),
                "finalizado": snapshot.get("finalizado", False),
                "asignaciones": self._jueces_reporte(tatami_id, ts),
            }

            try:
                sesion, cat = self._obtener_sesion_categoria(tatami_id, "figuras")
                if not sesion:
                    print(f"  [ERR] No existe categoría 'figuras' para guardar tatami {tatami_id}")
                    return

                combate = Combate(
                    sesion_tatami_id=sesion.id,
                    categoria_id=cat.id if cat else sesion.categoria_id,
                    nombre_hong=ganador.get("nombre") if ganador else snapshot.get("nombre_categoria", "Figuras"),
                    nombre_chung=snapshot.get("nombre_categoria", "Figuras"),
                    marcador_hong=float(ganador.get("total", 0)) if ganador else 0.0,
                    marcador_chung=0.0,
                    esq_hong=float(ganador.get("total", 0)) if ganador else 0.0,
                    esq_chung=0.0,
                    arb_hong=0.0,
                    arb_chung=0.0,
                    kyong_hong=0,
                    kyong_chung=0,
                    faltas_hong=0,
                    faltas_chung=0,
                    num_jueces=snapshot.get("num_jueces", 4),
                    duracion_segundos=0,
                    ronda_final="figuras",
                    historial_completo=snapshot.get("log", []),
                    jueces_detalle=jueces_detalle,
                    ganador="hong" if ganador else "empate",
                    fin=datetime.now(timezone.utc),
                )
                db.session.add(combate)
                db.session.commit()
                print(
                    f"  [OK] Figuras guardadas tatami {tatami_id}: "
                    f"{snapshot.get('nombre_categoria', 'Figuras')}"
                )
            except Exception as e:
                db.session.rollback()
                print(f"  [ERR] Error guardando figuras: {e}")
            return

        if not estado.get("historial"):
            return

        snapshot = guardar_combate_snapshot(estado)
        snapshot["jueces_detalle"]["asignaciones"] = self._jueces_reporte(tatami_id, ts)
        if llave_info:
            snapshot["jueces_detalle"]["llave"] = {
                "llave_id": llave_info.get("llave_id"),
                "nombre": llave_info.get("nombre"),
                "ronda_nombre": llave_info.get("ronda_nombre"),
            }
            snapshot["jueces_detalle"]["nombre_categoria"] = (
                f"{llave_info.get('nombre')} · {llave_info.get('ronda_nombre')}"
            )

        try:
            sesion, cat = self._obtener_sesion_categoria(tatami_id, "combate")
            if not sesion:
                print(f"  [ERR] No existe categoría 'combate' para guardar tatami {tatami_id}")
                return
            ts["sesion_id"] = sesion.id

            combate = Combate(
                sesion_tatami_id=sesion.id,
                categoria_id=cat.id if cat else sesion.categoria_id,
                nombre_hong=snapshot["nombre_hong"],
                nombre_chung=snapshot["nombre_chung"],
                marcador_hong=snapshot["marcador_hong"],
                marcador_chung=snapshot["marcador_chung"],
                esq_hong=snapshot["esq_hong"],
                esq_chung=snapshot["esq_chung"],
                arb_hong=snapshot["arb_hong"],
                arb_chung=snapshot["arb_chung"],
                kyong_hong=snapshot["kyong_hong"],
                kyong_chung=snapshot["kyong_chung"],
                faltas_hong=snapshot["faltas_hong"],
                faltas_chung=snapshot["faltas_chung"],
                num_jueces=snapshot["num_jueces"],
                duracion_segundos=snapshot["duracion_segundos"],
                ronda_final=snapshot["ronda_final"],
                historial_completo=snapshot["historial_completo"],
                jueces_detalle=snapshot["jueces_detalle"],
                ganador=snapshot.get("ganador_manual") or (
                    "hong" if snapshot["marcador_hong"] > snapshot["marcador_chung"]
                    else "chung" if snapshot["marcador_chung"] > snapshot["marcador_hong"]
                    else "empate"
                ),
                fin=datetime.now(timezone.utc),
            )
            db.session.add(combate)
            db.session.commit()

            # Avanza el número de combate del día para este tatami
            ts["num_combate"] = _num_combate_hoy(tatami_id)

            print(
                f"  [OK] Combate guardado tatami {tatami_id}: "
                f"{snapshot['nombre_hong']} vs {snapshot['nombre_chung']} "
                f"({snapshot['marcador_hong']} - {snapshot['marcador_chung']})"
            )
        except Exception as e:
            db.session.rollback()
            print(f"  [ERR] Error guardando combate: {e}")

    def _jueces_reporte(self, tatami_id, ts):
        jueces = {}
        try:
            asignaciones = AsignacionJuez.query.filter_by(tatami_id=int(tatami_id)).all()
            for asig in asignaciones:
                jueces[asig.rol_tatami] = _meta_desde_asignacion(asig)
        except Exception:
            pass

        for rol, meta in ts.get("jueces_meta", {}).items():
            if rol == "pantalla":
                continue
            if rol not in jueces or meta.get("origen") in ("directo", "pin"):
                jueces[rol] = {
                    "usuario_id": meta.get("usuario_id"),
                    "nombre": meta.get("nombre") or _rol_label(rol),
                    "email": meta.get("email") or "",
                    "rol_tatami": meta.get("rol_tatami") or rol,
                    "asignacion": meta.get("asignacion") or _rol_label(rol),
                    "origen": meta.get("origen") or "directo",
                    "asignado_at": meta.get("asignado_at"),
                    "asignado_por": meta.get("asignado_por"),
                }
        return jueces

    def _iniciar_crono(self, tatami_id):
        """Inicia el cronómetro del servidor para un tatami."""
        ts = _get_tatami_state(tatami_id)
        if ts["crono_activo"]:
            return
        ts["crono_activo"] = True
        room = _room_name(tatami_id)

        def tick():
            while ts["crono_activo"]:
                socketio.sleep(1)
                if not ts["crono_activo"]:
                    break
                estado_full = None
                crono_ligero = None
                # El snapshot se construye DENTRO del lock: copiar el estado
                # mientras otro hilo lo muta puede reventar este hilo (y el
                # cronómetro moriría en silencio para todos los dispositivos).
                with _lock:
                    estado = ts["estado"]
                    if not estado.get("activo"):
                        ts["crono_activo"] = False
                        break
                    if estado.get("segundos", 0) > 0:
                        estado["segundos"] -= 1
                    if estado.get("segundos", 0) <= 0:
                        # Fin del tiempo: los clientes DEBEN recibir el estado
                        # completo (activo=False + log de KuMan). Antes el
                        # break salía sin emitir y las pantallas quedaban con
                        # el crono "corriendo" en 0:00 sin el aviso de KuMan.
                        estado["segundos"] = 0
                        estado["activo"] = False
                        ts["crono_activo"] = False
                        _agregar_log(estado, "[TIEMPO] KuMan — Fin del tiempo", "arb")
                        estado_full = _build_estado_broadcast(ts)
                    else:
                        # Tick normal: solo viaja el segundero. El estado
                        # completo (log + historial) pesa demasiado para
                        # mandarlo cada segundo a decenas de dispositivos.
                        crono_ligero = {"segundos": estado["segundos"], "activo": True}
                if estado_full is not None:
                    socketio.emit("estado", {"datos": estado_full}, namespace="/combate", to=room)
                elif crono_ligero is not None:
                    socketio.emit("crono", crono_ligero, namespace="/combate", to=room)

        ts["crono_thread"] = socketio.start_background_task(tick)

    def _detener_crono(self, tatami_id):
        """Detiene el cronómetro del servidor."""
        ts = _get_tatami_state(tatami_id)
        ts["crono_activo"] = False
