"""
API: Llaves de eliminación directa (brackets)

- El admin crea una llave con la lista de competidores.
- El sistema los distribuye aleatoriamente y asigna byes automáticos
  (pases directos) cuando el número no es potencia de 2.
- Los ganadores avanzan ronda a ronda hasta la final.
"""

import io
import math
import random
import re
from datetime import datetime

from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required
from ..extensions import db
from ..models.campeonato import Campeonato
from ..models.tatami import Tatami
from ..models.llave import Llave
from ..filei18n import trad, idioma_request
from ..sede import sede_aqui
from .scoping import SOLO_PERSONAL, require_personal, es_dueno_campeonato, usuario_actual

llaves_bp = Blueprint("llaves", __name__)

# Traductor por defecto (español) para llamadas internas sin idioma explícito.
_T_ES = trad("es")
# Clave de traducción del nombre de ronda por nº de rondas restantes.
_RONDA_CLAVE = {1: "llave_final", 2: "llave_semifinal", 3: "llave_cuartos", 4: "llave_octavos"}


def _llave_fuera_de_workspace(user, llave):
    """True si un admin intenta tocar una llave de un campeonato ajeno."""
    if user is None or user.rol != "admin":
        return False
    camp = Campeonato.query.get(llave.campeonato_id)
    return not es_dueno_campeonato(user, camp)

MAX_COMPETIDORES = 64
# Figuras puntúa hasta 50 competidores (límite del motor de figuras)
MAX_COMPETIDORES_FIGURAS = 50
MIN_COMPETIDORES_FIGURAS = 2

RONDA_NOMBRES = {1: "Final", 2: "Semifinal", 3: "Cuartos", 4: "Octavos"}

# Sentinel de "ronda" para el partido por el 3er puesto (bronce). No vive en
# `rondas`, sino en `estructura["bronce"]`, para no tocar la lógica de avance.
BRONCE = "bronce"


def _comp_estructura(idx, c):
    """Competidor dentro de la estructura de una llave. Conserva la marca de
    categoría especial cuando viene (llaves generadas automáticamente)."""
    comp = {"id": idx + 1, "nombre": c["nombre"], "club": c.get("club") or ""}
    if c.get("especial"):
        comp["especial"] = True
    # El enlace con la ficha, cuando lo hay (llaves generadas desde F3). Lo que
    # lee una llave —el cuadro, el PDF, el socket, los reportes— solo mira
    # `nombre` y `club`, así que un campo más no le cambia nada a nadie. Los
    # partidos guardan este mismo diccionario, así que el podio lo hereda.
    if c.get("competidor_uid"):
        comp["competidor_uid"] = c["competidor_uid"]
    return comp


def generar_estructura_figuras(competidores):
    """
    Estructura de un grupo de figuras: solo la lista de competidores, sin
    sorteo ni cuadro. Se mantienen `rondas` y `campeon` vacíos para que el
    front comparta el mismo tipo de dato que las llaves de combate.
    """
    comps = [_comp_estructura(i, c) for i, c in enumerate(competidores)]
    return {"tipo": "figuras", "competidores": comps, "rondas": [], "campeon": None}


def _parse_competidores(data):
    return [
        {"nombre": str(c.get("nombre", "")).strip(), "club": str(c.get("club", "")).strip()}
        for c in (data.get("competidores") or [])
        if str(c.get("nombre", "")).strip()
    ]


def _validar_competidores(tipo, competidores):
    """Retorna un mensaje de error o None si la lista es válida para el tipo."""
    if tipo == "figuras":
        if len(competidores) < MIN_COMPETIDORES_FIGURAS:
            return (
                f"Un grupo de figuras necesita mínimo {MIN_COMPETIDORES_FIGURAS} "
                "competidores."
            )
        if len(competidores) > MAX_COMPETIDORES_FIGURAS:
            return f"Máximo {MAX_COMPETIDORES_FIGURAS} competidores en figuras."
        return None
    # Combate (eliminación)
    if len(competidores) < 3:
        return (
            "Una llave de eliminación necesita mínimo 3 competidores. "
            "Con solo 2, disputa un combate normal desde el tatami."
        )
    if len(competidores) > MAX_COMPETIDORES:
        return f"Máximo {MAX_COMPETIDORES} competidores"
    return None


def nombre_ronda(ronda_idx, total_rondas, t=None):
    """Nombre legible de una ronda: Final, Semifinal, Cuartos, ...
    Sin `t` responde en español (lo usan el socket y los datos guardados)."""
    t = t or _T_ES
    restantes = total_rondas - ronda_idx
    if restantes in _RONDA_CLAVE:
        return t(_RONDA_CLAVE[restantes])
    return t("llave_ronda_n", n=ronda_idx + 1)


def etiqueta_ronda(ronda_idx, total_rondas):
    """Como nombre_ronda, pero reconoce el partido por el bronce."""
    if ronda_idx == BRONCE:
        return "3er puesto"
    return nombre_ronda(ronda_idx, total_rondas)


def _semifinal_idx(estructura):
    """Índice de la ronda de semifinales (penúltima) o None."""
    rondas = estructura.get("rondas", [])
    return len(rondas) - 2 if len(rondas) >= 2 else None


def _actualizar_bronce(estructura):
    """
    Rellena `estructura["bronce"]` con los perdedores de las semifinales:
    - 2 perdedores reales → partido por el bronce a disputar.
    - 1 perdedor real y la otra semifinal fue un BYE → 3° directo sin disputa.
    - 1 perdedor real y la otra semifinal AÚN NO se juega → bronce en espera
      (sin ganador: el rival saldrá al terminar esa semifinal).
    - 0 → no hay bronce.
    Conserva el ganador del bronce si los competidores no cambiaron.
    """
    semi_idx = _semifinal_idx(estructura)
    if semi_idx is None:
        estructura.pop("bronce", None)
        return
    perdedores = []
    semi_pendiente = False
    for p in estructura["rondas"][semi_idx]:
        if p.get("ganador") in (1, 2) and p.get("comp1") and p.get("comp2"):
            perdedores.append(p["comp2"] if p["ganador"] == 1 else p["comp1"])
        elif p.get("ganador") in (1, 2):
            # Bye ya resuelto (un solo competidor): nunca producirá perdedor.
            perdedores.append(None)
        else:
            # Semifinal sin jugar (o esperando a sus clasificados): SÍ va a
            # producir un perdedor más adelante — el bronce debe esperar.
            perdedores.append(None)
            semi_pendiente = True
    reales = [x for x in perdedores if x]
    actual = estructura.get("bronce") or {}

    if len(reales) >= 2:
        comp1, comp2 = perdedores[0], perdedores[1]
        mismos = (
            (actual.get("comp1") or {}).get("id") == comp1["id"]
            and (actual.get("comp2") or {}).get("id") == comp2["id"]
        )
        estructura["bronce"] = {
            "comp1": comp1,
            "comp2": comp2,
            "ganador": actual.get("ganador") if mismos else None,
        }
    elif len(reales) == 1 and semi_pendiente:
        # El rival del bronce todavía no existe: partido en espera. (Antes se
        # adjudicaba el 3° automáticamente apenas caía el primer semifinalista,
        # como si la otra semifinal fuera un bye.)
        estructura["bronce"] = {"comp1": reales[0], "comp2": None, "ganador": None}
    elif len(reales) == 1:
        # Bye en la otra semifinal: el único perdedor real es 3° sin disputar.
        estructura["bronce"] = {"comp1": reales[0], "comp2": None, "ganador": 1}
    else:
        estructura.pop("bronce", None)


def partidos_jugables(estructura):
    """Partidos con ambos competidores definidos y sin ganador, en orden.
    Incluye el partido por el bronce cuando hay dos semifinalistas."""
    jugables = []
    for r, ronda in enumerate(estructura.get("rondas", [])):
        for i, p in enumerate(ronda):
            if p.get("ganador") is None and p.get("comp1") and p.get("comp2"):
                jugables.append((r, i, p))
    bronce = estructura.get("bronce")
    if bronce and bronce.get("comp1") and bronce.get("comp2") and bronce.get("ganador") is None:
        jugables.append((BRONCE, 0, bronce))
    return jugables


def siguiente_partido(estructura):
    """
    Elige el siguiente combate a disputar.
    Se intenta que los peleadores del último combate jugado no vuelvan
    a pelear de inmediato (descanso), cuando hay otra opción disponible.
    Retorna (ronda_idx, partido_idx, partido) o None si no quedan.
    """
    jugables = partidos_jugables(estructura)
    if not jugables:
        return None
    ultimo = estructura.get("ultimo_jugado") or []
    ids_descansando = set(ultimo)
    if ids_descansando:
        for r, i, p in jugables:
            ids = {p["comp1"]["id"], p["comp2"]["id"]}
            if not (ids & ids_descansando):
                return (r, i, p)
    return jugables[0]


def registrar_resultado(estructura, ronda_idx, partido_idx, ganador):
    """
    Marca (o corrige) el ganador de un partido, propaga el avance y
    registra quiénes acaban de pelear (para darles descanso).
    Lanza ValueError si el partido o el lado no son válidos.
    """
    if ganador not in (1, 2, None):
        raise ValueError("ganador debe ser 1, 2 o null")

    # Partido por el bronce: vive aparte, no avanza a ninguna ronda.
    if ronda_idx == BRONCE:
        bronce = estructura.get("bronce")
        if not bronce or not bronce.get("comp1") or not bronce.get("comp2"):
            raise ValueError("No hay partido por el bronce disponible")
        bronce["ganador"] = ganador
        if ganador is not None:
            estructura["ultimo_jugado"] = [bronce["comp1"]["id"], bronce["comp2"]["id"]]
        return estructura

    rondas = estructura.get("rondas", [])
    if not (0 <= ronda_idx < len(rondas)) or not (0 <= partido_idx < len(rondas[ronda_idx])):
        raise ValueError("Partido no encontrado")

    partido = rondas[ronda_idx][partido_idx]
    if ganador == 1 and not partido.get("comp1"):
        raise ValueError("Ese lado del partido está vacío")
    if ganador == 2 and not partido.get("comp2"):
        raise ValueError("Ese lado del partido está vacío")
    # En rondas posteriores a la primera, un lado vacío significa que el rival
    # aún no se define (su partido previo no terminó). Marcar ganador ahí
    # registraría un triunfo sin disputa y corrompería el avance del cuadro.
    # (En la primera ronda un lado vacío es un bye legítimo.)
    if (
        ganador is not None
        and ronda_idx > 0
        and (not partido.get("comp1") or not partido.get("comp2"))
    ):
        raise ValueError(
            "Ese partido aún no tiene rival definido: completa primero la ronda anterior"
        )

    _limpiar_descendientes(estructura, ronda_idx, partido_idx)
    partido["ganador"] = ganador
    if ganador is not None:
        _avanzar(estructura, ronda_idx, partido_idx)
        if partido.get("comp1") and partido.get("comp2"):
            estructura["ultimo_jugado"] = [
                partido["comp1"]["id"], partido["comp2"]["id"],
            ]
    # Tras cualquier cambio en semifinales, recalcular el partido por el bronce.
    _actualizar_bronce(estructura)
    return estructura


def podio_llave(estructura, con_uid=False):
    """
    Podio de una llave de eliminación a partir del cuadro:
    1° campeón · 2° finalista perdedor · 3° ganador del partido por el bronce
    (un único tercer puesto, disputado entre los perdedores de semifinales).
    Retorna [] si todavía no hay campeón.

    `con_uid` añade el uid de la ficha de cada puesto, cuando lo hay. Apagado
    por defecto A PROPÓSITO: este podio alimenta los resultados PÚBLICOS, y el
    uid es interno (`app/uid.py`). Solo lo pide quien necesita saber de quién
    es cada puesto: el panel del competidor.
    """
    estructura = estructura or {}
    rondas = estructura.get("rondas") or []
    if not estructura.get("campeon") or not rondas:
        return []

    def _comp(c, puesto):
        item = {"puesto": puesto, "nombre": c.get("nombre", "-"), "club": c.get("club", "")}
        if con_uid and c.get("competidor_uid"):
            item["competidor_uid"] = c["competidor_uid"]
        return item

    podio = []
    final = rondas[-1][0] if rondas[-1] else None
    if final and final.get("ganador") in (1, 2):
        gan = final["comp1"] if final["ganador"] == 1 else final["comp2"]
        perd = final["comp2"] if final["ganador"] == 1 else final["comp1"]
        if gan:
            podio.append(_comp(gan, 1))
        if perd:
            podio.append(_comp(perd, 2))
    # 3°: ganador del partido por el bronce (un único 3°, sin bronce compartido).
    bronce = estructura.get("bronce") or {}
    if bronce.get("ganador") in (1, 2):
        tercero = bronce["comp1"] if bronce["ganador"] == 1 else bronce["comp2"]
        if tercero:
            podio.append(_comp(tercero, 3))
    return podio


def _info_siguiente(llave):
    """Resumen para el panel del Juez Central según el tipo de llave."""
    estructura = llave.estructura or {}
    competidores = estructura.get("competidores", [])

    # Figuras: no hay cuadro; solo importa el grupo y su estado.
    if llave.tipo_norm == "figuras":
        return {
            "num_competidores": len(competidores),
            "pendientes": 0,
            "siguiente": None,
            "campeon": None,
        }

    # Combate: siguiente partido sugerido.
    sig = siguiente_partido(estructura)
    total = len(estructura.get("rondas", []))
    return {
        "num_competidores": len(competidores),
        "pendientes": len(partidos_jugables(estructura)),
        "siguiente": None if sig is None else {
            "ronda": sig[0],
            "partido": sig[1],
            "ronda_nombre": etiqueta_ronda(sig[0], total),
            "comp1": sig[2]["comp1"],
            "comp2": sig[2]["comp2"],
        },
        "campeon": estructura.get("campeon"),
    }


def _require_admin():
    from .scoping import require_admin
    return require_admin()


def generar_estructura(competidores):
    """
    Genera la estructura del bracket:
    - Sorteo aleatorio de competidores.
    - Tamaño = siguiente potencia de 2; los byes se reparten para que
      ningún competidor enfrente a otro bye en la primera ronda.
    - Los byes avanzan automáticamente a la segunda ronda.
    """
    comps = [_comp_estructura(i, c) for i, c in enumerate(competidores)]
    random.shuffle(comps)

    n = len(comps)
    size = 2 ** max(1, math.ceil(math.log2(n))) if n > 1 else 2
    num_byes = size - n

    # Primera ronda: los primeros `num_byes` sorteados reciben bye;
    # el resto se empareja en orden de sorteo.
    partidos_r0 = []
    for i in range(num_byes):
        partidos_r0.append({"comp1": comps[i], "comp2": None, "ganador": None})
    resto = comps[num_byes:]
    for i in range(0, len(resto), 2):
        comp2 = resto[i + 1] if i + 1 < len(resto) else None
        partidos_r0.append({"comp1": resto[i], "comp2": comp2, "ganador": None})
    # Mezclar el orden de los partidos para repartir los byes en el cuadro
    random.shuffle(partidos_r0)

    # Rondas siguientes vacías
    rondas = [partidos_r0]
    partidos_en_ronda = len(partidos_r0)
    while partidos_en_ronda > 1:
        partidos_en_ronda //= 2
        rondas.append([
            {"comp1": None, "comp2": None, "ganador": None}
            for _ in range(partidos_en_ronda)
        ])

    estructura = {"competidores": comps, "rondas": rondas, "campeon": None}

    # Avanzar byes automáticamente
    for idx, partido in enumerate(rondas[0]):
        if partido["comp1"] and not partido["comp2"]:
            partido["ganador"] = 1
            _avanzar(estructura, 0, idx)
    # Inicializa el partido por el bronce (vacío hasta jugar las semifinales).
    _actualizar_bronce(estructura)
    return estructura


def _avanzar(estructura, ronda_idx, partido_idx):
    """Coloca al ganador de un partido en su lugar de la siguiente ronda."""
    rondas = estructura["rondas"]
    partido = rondas[ronda_idx][partido_idx]
    ganador = None
    if partido["ganador"] == 1:
        ganador = partido["comp1"]
    elif partido["ganador"] == 2:
        ganador = partido["comp2"]

    if ronda_idx == len(rondas) - 1:
        estructura["campeon"] = ganador
        return

    siguiente = rondas[ronda_idx + 1][partido_idx // 2]
    slot = "comp1" if partido_idx % 2 == 0 else "comp2"
    siguiente[slot] = ganador


def _limpiar_descendientes(estructura, ronda_idx, partido_idx):
    """
    Si se corrige un resultado, borra todo lo que dependía de él
    (ganadores y posiciones en rondas siguientes).
    """
    rondas = estructura["rondas"]
    if ronda_idx == len(rondas) - 1:
        estructura["campeon"] = None
        return
    sig_idx = partido_idx // 2
    siguiente = rondas[ronda_idx + 1][sig_idx]
    slot = "comp1" if partido_idx % 2 == 0 else "comp2"
    if siguiente[slot] is not None or siguiente["ganador"] is not None:
        siguiente[slot] = None
        siguiente["ganador"] = None
        _limpiar_descendientes(estructura, ronda_idx + 1, sig_idx)


@llaves_bp.route("", methods=["POST"])
@jwt_required()
@sede_aqui
def crear():
    """
    POST /api/llaves
    Body: {
      "campeonato_id", "nombre", "tipo"?: "combate"|"figuras",
      "descripcion"?, "tatami_id"?, "competidores": [{"nombre", "club"?}]
    }
    El tatami es opcional: sin tatami la llave queda en el pool (pendiente)
    para asignarse después.
    """
    admin = _require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    data = request.get_json() or {}
    campeonato_id = data.get("campeonato_id")
    tatami_id = data.get("tatami_id")
    tipo = (data.get("tipo") or "combate").strip().lower()
    nombre = (data.get("nombre") or "").strip()
    descripcion = (data.get("descripcion") or "").strip()
    competidores = _parse_competidores(data)

    if tipo not in ("combate", "figuras"):
        return jsonify({"error": "Tipo de llave inválido"}), 400
    camp = Campeonato.query.get(campeonato_id) if campeonato_id else None
    if not camp or not es_dueno_campeonato(admin, camp):
        return jsonify({"error": "Campeonato no encontrado"}), 404
    if not nombre:
        return jsonify({"error": "El nombre de la categoría es requerido"}), 400

    # El tatami (opcional) es donde se disputará esta llave
    tatami = None
    if tatami_id:
        tatami = Tatami.query.get(int(tatami_id))
        if not tatami or tatami.campeonato_id != int(campeonato_id):
            return jsonify({"error": "El tatami no pertenece a este campeonato"}), 400

    error = _validar_competidores(tipo, competidores)
    if error:
        return jsonify({"error": error}), 400

    estructura = (
        generar_estructura_figuras(competidores) if tipo == "figuras"
        else generar_estructura(competidores)
    )
    llave = Llave(
        campeonato_id=int(campeonato_id),
        tatami_id=tatami.id if tatami else None,
        tipo=tipo,
        nombre=nombre[:120],
        descripcion=descripcion[:500] or None,
        estado="pendiente",
        estructura=estructura,
        created_by=admin.id,
    )
    db.session.add(llave)
    db.session.commit()
    mensaje = (
        "Grupo de figuras creado" if tipo == "figuras"
        else "Llave creada con sorteo aleatorio"
    )
    return jsonify({
        "message": mensaje,
        "llave": llave.to_dict(tatami_numero=tatami.numero if tatami else None),
    }), 201


@llaves_bp.route("/<int:llave_id>", methods=["PUT"])
@jwt_required()
@sede_aqui
def editar(llave_id):
    """
    PUT /api/llaves/:id
    Edita una llave SOLO si está pendiente (no activa ni terminada): nombre,
    descripción, tatami (incluido dejarla sin asignar) y competidores.
    Body: { "nombre"?, "descripcion"?, "tatami_id"?: int|null, "competidores"? }
    """
    admin = _require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    llave = Llave.query.get_or_404(llave_id)
    if _llave_fuera_de_workspace(admin, llave):
        return jsonify({"error": "Llave no encontrada"}), 404
    if llave.estado_norm != "pendiente":
        return jsonify({
            "error": "Solo se pueden editar llaves pendientes. Una llave activa "
                     "o terminada no se modifica para no corromper resultados."
        }), 409

    data = request.get_json() or {}
    tipo = llave.tipo_norm

    if "nombre" in data:
        nombre = (data.get("nombre") or "").strip()
        if not nombre:
            return jsonify({"error": "El nombre de la categoría es requerido"}), 400
        llave.nombre = nombre[:120]

    if "descripcion" in data:
        llave.descripcion = (data.get("descripcion") or "").strip()[:500] or None

    if "tatami_id" in data:
        tatami_id = data.get("tatami_id")
        if tatami_id in (None, "", 0):
            llave.tatami_id = None
        else:
            tatami = Tatami.query.get(int(tatami_id))
            if not tatami or tatami.campeonato_id != llave.campeonato_id:
                return jsonify({"error": "El tatami no pertenece a este campeonato"}), 400
            llave.tatami_id = tatami.id

    if "competidores" in data:
        competidores = _parse_competidores(data)
        error = _validar_competidores(tipo, competidores)
        if error:
            return jsonify({"error": error}), 400
        # Re-sortear SOLO si la lista realmente cambió: el formulario de
        # edición siempre reenvía los competidores, y al cambiar solo el
        # nombre o el tatami el cuadro (ya sorteado y quizá anunciado) no
        # debe volver a barajarse.
        actuales = sorted(
            (c.get("nombre", ""), c.get("club") or "")
            for c in (llave.estructura or {}).get("competidores", [])
        )
        nuevos = sorted((c["nombre"], c.get("club") or "") for c in competidores)
        if nuevos != actuales:
            _conservar_enlaces(competidores, llave.estructura)
            llave.estructura = (
                generar_estructura_figuras(competidores) if tipo == "figuras"
                else generar_estructura(competidores)
            )

    db.session.commit()
    return jsonify({
        "message": "Llave actualizada",
        "llave": _con_numero_tatami([llave])[0],
    }), 200


def _con_numero_tatami(llaves):
    """Adjunta el número de tatami a cada llave (una consulta por lote)."""
    tatami_ids = {l.tatami_id for l in llaves if l.tatami_id}
    numeros = {}
    if tatami_ids:
        for t in Tatami.query.filter(Tatami.id.in_(tatami_ids)).all():
            numeros[t.id] = t.numero
    return [l.to_dict(tatami_numero=numeros.get(l.tatami_id)) for l in llaves]


@llaves_bp.route("/campeonato/<int:camp_id>", methods=["GET"])
@jwt_required()
def listar_por_campeonato(camp_id):
    """GET /api/llaves/campeonato/:id — Llaves de un campeonato."""
    user = require_personal()
    if not user:
        return jsonify({"error": SOLO_PERSONAL}), 403
    if user.rol == "admin":
        camp = Campeonato.query.get(camp_id)
        if not camp or not es_dueno_campeonato(user, camp):
            return jsonify({"error": "Campeonato no encontrado"}), 404
    llaves = (
        Llave.query.filter_by(campeonato_id=camp_id)
        .order_by(Llave.created_at.desc())
        .all()
    )
    return jsonify(_con_numero_tatami(llaves)), 200


@llaves_bp.route("/tatami/<int:tatami_id>", methods=["GET"])
@jwt_required()
def listar_por_tatami(tatami_id):
    """
    GET /api/llaves/tatami/:id — Llaves asignadas a un tatami, con el
    siguiente combate sugerido (lo usa el panel del Juez Central).
    """
    # El panel del tatami es de jueces: la guarda los deja pasar a todos.
    user = require_personal()
    if not user:
        return jsonify({"error": SOLO_PERSONAL}), 403
    llaves = (
        Llave.query.filter_by(tatami_id=tatami_id)
        .order_by(Llave.created_at.asc())
        .all()
    )
    result = []
    for llave_obj, datos in zip(llaves, _con_numero_tatami(llaves)):
        datos.update(_info_siguiente(llave_obj))
        # El cuadro completo no hace falta en el panel del tatami
        datos.pop("estructura", None)
        result.append(datos)
    return jsonify(result), 200


@llaves_bp.route("/<int:llave_id>", methods=["GET"])
@jwt_required()
def obtener(llave_id):
    """GET /api/llaves/:id — Detalle de una llave."""
    user = require_personal()
    if not user:
        return jsonify({"error": SOLO_PERSONAL}), 403
    llave = Llave.query.get_or_404(llave_id)
    if _llave_fuera_de_workspace(user, llave):
        return jsonify({"error": "Llave no encontrada"}), 404
    return jsonify(_con_numero_tatami([llave])[0]), 200


@llaves_bp.route("/<int:llave_id>/partido", methods=["PUT"])
@jwt_required()
@sede_aqui
def marcar_ganador(llave_id):
    """
    PUT /api/llaves/:id/partido
    Body: { "ronda": 0, "partido": 1, "ganador": 1|2|null }
    Marca (o corrige) el ganador de un partido y avanza el cuadro.
    """
    admin = _require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    llave = Llave.query.get_or_404(llave_id)
    if _llave_fuera_de_workspace(admin, llave):
        return jsonify({"error": "Llave no encontrada"}), 404
    if llave.tipo_norm != "combate":
        return jsonify({"error": "Solo las llaves de combate tienen partidos."}), 400
    data = request.get_json() or {}

    # El partido por el bronce se direcciona con ronda == "bronce".
    if data.get("ronda") == BRONCE:
        ronda_idx, partido_idx = BRONCE, 0
    else:
        try:
            ronda_idx = int(data.get("ronda"))
            partido_idx = int(data.get("partido"))
        except (TypeError, ValueError):
            return jsonify({"error": "ronda y partido son requeridos"}), 400

    ganador = data.get("ganador")

    # Copia profunda: la columna JSON requiere reasignar el objeto completo
    import copy
    estructura = copy.deepcopy(llave.estructura)
    try:
        registrar_resultado(estructura, ronda_idx, partido_idx, ganador)
    except ValueError as e:
        codigo = 404 if "no encontrado" in str(e) else 400
        return jsonify({"error": str(e)}), codigo

    llave.estructura = estructura
    # La llave queda terminada cuando ya no quedan partidos por jugar (incluido
    # el bronce); si se corrige un resultado y reaparece alguno, vuelve a abrir.
    if estructura.get("campeon") and not partidos_jugables(estructura):
        llave.estado = "terminada"
    elif llave.estado_norm == "terminada":
        llave.estado = "pendiente"
    db.session.commit()
    return jsonify({
        "message": "Resultado registrado",
        "llave": _con_numero_tatami([llave])[0],
    }), 200


def _pdf_llave(llave, tatami_numero=None, t=None):
    """
    PDF del cuadro de una llave de combate (para publicar el sorteo en
    cartelera) o de la lista de un grupo de figuras. Una página apaisada.
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas as pdfcanvas

    t = t or _T_ES
    est = llave.estructura or {}
    W, H = landscape(A4)
    buf = io.BytesIO()
    c = pdfcanvas.Canvas(buf, pagesize=landscape(A4))

    GOLD = colors.HexColor("#B8860B")
    GOLD_BG = colors.HexColor("#FDF3D0")
    DARK = colors.HexColor("#1A1A2E")
    GRIS = colors.HexColor("#888888")
    BORDE = colors.HexColor("#BBBBBB")

    # ── Encabezado ──
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(40, H - 45, llave.nombre[:70])
    c.setFont("Helvetica", 9)
    c.setFillColor(GRIS)
    sub = "DINAMYT — " + (
        t("llave_grupo_figuras") if llave.tipo_norm == "figuras" else t("llave_cuadro")
    )
    if tatami_numero:
        sub += " · " + t("tatami_n", n=tatami_numero)
    sub += " · " + t("llave_generado", fecha=datetime.now().strftime('%d/%m/%Y %H:%M'))
    if llave.descripcion:
        sub += f" · {llave.descripcion[:70]}"
    c.drawString(40, H - 60, sub)
    c.setStrokeColor(BORDE)
    c.line(40, H - 68, W - 40, H - 68)

    top = H - 92
    bottom = 40
    usable_h = top - bottom

    # ── Grupo de figuras: lista de competidores en columnas ──
    if llave.tipo_norm == "figuras":
        comps = est.get("competidores") or []
        por_col = 22
        n_cols = max(1, -(-len(comps) // por_col))
        col_w = (W - 80) / n_cols
        c.setFont("Helvetica", 10)
        for i, comp in enumerate(comps):
            col, fila = divmod(i, por_col)
            x = 40 + col * col_w
            y = top - 10 - fila * 20
            c.setFillColor(GRIS)
            c.drawString(x, y, f"{i + 1}.")
            c.setFillColor(DARK)
            texto = comp.get("nombre", "-")
            if comp.get("club"):
                texto += f"  ({comp['club']})"
            c.drawString(x + 22, y, texto[:52])
        c.showPage()
        c.save()
        buf.seek(0)
        return buf

    # ── Cuadro de eliminación ──
    rondas = est.get("rondas") or []
    n_cols = len(rondas) + 1
    col_w = (W - 80) / max(1, n_cols)
    box_w = col_w - 16

    def _texto_lado(comp, es_bye):
        if comp:
            texto = comp.get("nombre") or "-"
            if comp.get("club"):
                texto += f" ({comp['club']})"
            return texto
        return t("llave_bye") if es_bye else t("llave_por_definir")

    def _caja_partido(x, y_c, h, comp1, comp2, ganador, font, bye_abajo=False):
        mitades = [(1, comp1, y_c, y_c + h / 2, False),
                   (2, comp2, y_c - h / 2, y_c, bye_abajo)]
        for lado, comp, y0, y1, _b in mitades:
            if ganador == lado and comp:
                c.setFillColor(GOLD_BG)
                c.rect(x, y0, box_w, y1 - y0, stroke=0, fill=1)
        c.setStrokeColor(BORDE)
        c.setLineWidth(0.7)
        c.rect(x, y_c - h / 2, box_w, h, stroke=1, fill=0)
        c.line(x, y_c, x + box_w, y_c)
        for lado, comp, y0, y1, es_bye in mitades:
            gana = ganador == lado and comp
            c.setFont("Helvetica-Bold" if gana else "Helvetica", font)
            c.setFillColor(DARK if comp else GRIS)
            max_chars = max(6, int((box_w - 8) / (font * 0.52)))
            c.drawString(
                x + 4, (y0 + y1) / 2 - font * 0.35,
                _texto_lado(comp, es_bye)[:max_chars],
            )

    for r, ronda in enumerate(rondas):
        x = 40 + r * col_w
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(GOLD)
        c.drawCentredString(x + box_w / 2, top + 8, nombre_ronda(r, len(rondas), t).upper())
        m = max(1, len(ronda))
        slot = usable_h / m
        h_box = max(14, min(38, slot - 8))
        font = 8 if h_box >= 26 else max(4.6, h_box / 3.2)
        for i, p in enumerate(ronda):
            y_c = top - slot * i - slot / 2
            es_bye = r == 0 and p.get("comp1") and not p.get("comp2")
            _caja_partido(
                x, y_c, h_box, p.get("comp1"), p.get("comp2"),
                p.get("ganador"), font, bye_abajo=bool(es_bye),
            )

    # Columna final: campeón + bronce + podio
    x = 40 + len(rondas) * col_w
    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(GOLD)
    c.drawCentredString(x + box_w / 2, top + 8, t("llave_campeon"))
    campeon = est.get("campeon")
    y_camp = top - usable_h / 2 + 40
    c.setStrokeColor(GOLD if campeon else BORDE)
    if campeon:
        c.setFillColor(GOLD_BG)
        c.rect(x, y_camp - 14, box_w, 28, stroke=1, fill=1)
    else:
        c.rect(x, y_camp - 14, box_w, 28, stroke=1, fill=0)
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(DARK if campeon else GRIS)
    c.drawCentredString(
        x + box_w / 2, y_camp - 3.5,
        (campeon.get("nombre") if campeon else t("llave_por_definir"))[:26],
    )

    bronce = est.get("bronce")
    if bronce and (bronce.get("comp1") or bronce.get("comp2")):
        y_b = y_camp - 74
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(GOLD)
        c.drawCentredString(x + box_w / 2, y_b + 26, t("llave_3er"))
        _caja_partido(
            x, y_b, 30, bronce.get("comp1"), bronce.get("comp2"),
            bronce.get("ganador"), 7.5,
            bye_abajo=bool(not bronce.get("comp2") and bronce.get("ganador") == 1),
        )

    podio = podio_llave(est)
    if podio:
        y_p = y_camp - 140
        c.setFont("Helvetica-Bold", 9)
        c.setFillColor(GOLD)
        c.drawString(x, y_p + 14, t("llave_podio"))
        c.setFillColor(DARK)
        for item in podio:
            c.setFont("Helvetica-Bold", 8.5)
            c.drawString(x, y_p, f"{item['puesto']}°")
            c.setFont("Helvetica", 8.5)
            c.drawString(x + 16, y_p, f"{item['nombre']}"[:30])
            y_p -= 13

    c.showPage()
    c.save()
    buf.seek(0)
    return buf


@llaves_bp.route("/<int:llave_id>/export/pdf", methods=["GET"])
@jwt_required()
def exportar_pdf_llave(llave_id):
    """GET /api/llaves/:id/export/pdf — Cuadro de la llave para imprimir."""
    admin = _require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    llave = Llave.query.get_or_404(llave_id)
    if _llave_fuera_de_workspace(admin, llave):
        return jsonify({"error": "Llave no encontrada"}), 404
    tatami = Tatami.query.get(llave.tatami_id) if llave.tatami_id else None
    try:
        output = _pdf_llave(llave, tatami.numero if tatami else None, trad(idioma_request()))
    except ImportError:
        return jsonify({
            "error": "No se pudo generar PDF: falta reportlab. Instala "
                     "dependencias con pip install -r requirements.txt."
        }), 500

    slug = re.sub(r"[^A-Za-z0-9]+", "-", llave.nombre).strip("-").lower()[:40] or "llave"
    nombre = f"dinamyt_llave_{slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return send_file(
        output,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=nombre,
    )


@llaves_bp.route("/<int:llave_id>", methods=["DELETE"])
@jwt_required()
@sede_aqui
def eliminar(llave_id):
    """DELETE /api/llaves/:id — Eliminar una llave."""
    admin = _require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    llave = Llave.query.get_or_404(llave_id)
    if _llave_fuera_de_workspace(admin, llave):
        return jsonify({"error": "Llave no encontrada"}), 404
    # Capturar el nombre ANTES de borrar: tras el commit el objeto queda
    # expirado y acceder a sus atributos lanza ObjectDeletedError (500).
    nombre = llave.nombre
    db.session.delete(llave)
    db.session.commit()
    return jsonify({"message": f"Llave '{nombre}' eliminada"}), 200


# ══════════════════════════════════════════════════════════════════
#  Combinar llaves y mover competidores entre llaves
#  (solo llaves PENDIENTES: las activas/terminadas no se tocan para
#   no corromper resultados ya disputados)
# ══════════════════════════════════════════════════════════════════

def _comp_plano(c):
    """Un competidor de una estructura, listo para volver a sortearse.

    Conserva el enlace con su ficha: combinar y mover re-sortean el cuadro, y
    si el uid se quedara por el camino, el resultado de esa llave volvería a no
    ser de nadie.
    """
    d = {"nombre": c.get("nombre", ""), "club": c.get("club") or ""}
    if c.get("especial"):
        d["especial"] = True
    if c.get("competidor_uid"):
        d["competidor_uid"] = c["competidor_uid"]
    return d


def _comps_planos(estructura):
    """Competidores de una estructura como lista plana {nombre, club, especial, uid}."""
    return [_comp_plano(c) for c in (estructura or {}).get("competidores", [])]


def _conservar_enlaces(nuevos, estructura):
    """Devuelve a cada competidor editado el uid que ya tenía en la llave.

    El formulario de edición solo manda nombres y clubes, y cambiar la lista
    regenera la llave entera: sin esto, añadir UN competidor le quitaba el
    enlace a todos los demás.

    Se empareja por nombre y club. Si en la llave había dos homónimos con fichas
    distintas, **no se adivina**: ninguno de los dos recupera el enlace, porque
    colgarle un resultado a la persona equivocada es peor que no colgarlo.
    """
    def clave(c):
        return (str(c.get("nombre", "")).strip().lower(),
                str(c.get("club", "") or "").strip().lower())

    por_clave, ambiguos = {}, set()
    for c in (estructura or {}).get("competidores", []):
        uid = c.get("competidor_uid")
        if not uid:
            continue
        k = clave(c)
        if k in por_clave and por_clave[k] != uid:
            ambiguos.add(k)
        por_clave[k] = uid
    for c in nuevos:
        k = clave(c)
        if k in por_clave and k not in ambiguos:
            c["competidor_uid"] = por_clave[k]
    return nuevos


def _regenerar(tipo, competidores):
    """Nueva estructura (con sorteo si es combate) para la lista dada."""
    return (
        generar_estructura_figuras(competidores) if tipo == "figuras"
        else generar_estructura(competidores)
    )


@llaves_bp.route("/combinar", methods=["POST"])
@jwt_required()
@sede_aqui
def combinar():
    """
    POST /api/llaves/combinar
    Body: { "llave_ids": [..], "nombre"?: str, "tatami_id"?: int|null }
    Fusiona 2+ llaves PENDIENTES del mismo campeonato y tipo en UNA nueva:
    concatena los competidores (sin duplicar nombre+club), re-sortea el cuadro
    y elimina las llaves originales. Sin `nombre`, conserva el de la primera;
    sin `tatami_id`, conserva el tatami de la primera.
    """
    admin = _require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    data = request.get_json() or {}
    try:
        ids = [int(x) for x in (data.get("llave_ids") or [])]
    except (TypeError, ValueError):
        return jsonify({"error": "llave_ids inválidos"}), 400
    ids = list(dict.fromkeys(ids))  # únicos conservando el orden
    if len(ids) < 2:
        return jsonify({"error": "Selecciona al menos 2 llaves para combinar."}), 400

    llaves = Llave.query.filter(Llave.id.in_(ids)).all()
    por_id = {l.id: l for l in llaves}
    if len(por_id) != len(ids):
        return jsonify({"error": "Alguna de las llaves no existe."}), 404
    for l in llaves:
        if _llave_fuera_de_workspace(admin, l):
            return jsonify({"error": "Llave no encontrada"}), 404
    if len({l.campeonato_id for l in llaves}) != 1:
        return jsonify({"error": "Solo se pueden combinar llaves del mismo campeonato."}), 400
    tipos = {l.tipo_norm for l in llaves}
    if len(tipos) != 1:
        return jsonify({"error": "No se puede combinar una llave de combate con un grupo de figuras."}), 400
    if any(l.estado_norm != "pendiente" for l in llaves):
        return jsonify({
            "error": "Solo se pueden combinar llaves pendientes. Las activas o "
                     "terminadas no se tocan para no perder resultados."
        }), 409

    tipo = tipos.pop()
    primera = por_id[ids[0]]

    # Unión de competidores en el orden de selección, sin duplicados
    competidores, vistos = [], set()
    for lid in ids:
        for c in _comps_planos(por_id[lid].estructura):
            clave = (c["nombre"].strip().lower(), c["club"].strip().lower())
            if not c["nombre"].strip() or clave in vistos:
                continue
            vistos.add(clave)
            competidores.append(c)

    error = _validar_competidores(tipo, competidores)
    if error:
        return jsonify({"error": error}), 400

    # Tatami de la nueva llave: el del body o el de la primera seleccionada
    tatami = None
    if "tatami_id" in data:
        tid = data.get("tatami_id")
        if tid not in (None, "", 0):
            tatami = Tatami.query.get(int(tid))
            if not tatami or tatami.campeonato_id != primera.campeonato_id:
                return jsonify({"error": "El tatami no pertenece a este campeonato"}), 400
    elif primera.tatami_id:
        tatami = Tatami.query.get(primera.tatami_id)

    nombre = (data.get("nombre") or "").strip() or primera.nombre
    nueva = Llave(
        campeonato_id=primera.campeonato_id,
        tatami_id=tatami.id if tatami else None,
        tipo=tipo,
        nombre=nombre[:120],
        descripcion=primera.descripcion,
        estado="pendiente",
        estructura=_regenerar(tipo, competidores),
        created_by=admin.id,
    )
    db.session.add(nueva)
    for l in llaves:
        db.session.delete(l)
    db.session.commit()

    return jsonify({
        "message": f"{len(ids)} llaves combinadas en '{nueva.nombre}' "
                   f"({len(competidores)} competidores, sorteo nuevo)",
        "llave": _con_numero_tatami([nueva])[0],
    }), 201


@llaves_bp.route("/mover-competidor", methods=["POST"])
@jwt_required()
@sede_aqui
def mover_competidor():
    """
    POST /api/llaves/mover-competidor
    Body: { "origen_id": int, "destino_id": int, "competidor_id": int }
    Mueve un competidor entre dos llaves PENDIENTES del mismo campeonato y
    tipo; ambos cuadros se re-sortean. Si el origen queda vacío, se elimina.
    Si quedaría por debajo del mínimo (sin quedar vacío), se rechaza y se
    sugiere combinar las llaves.
    """
    admin = _require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    data = request.get_json() or {}
    try:
        origen_id = int(data.get("origen_id"))
        destino_id = int(data.get("destino_id"))
        competidor_id = int(data.get("competidor_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "origen_id, destino_id y competidor_id son requeridos"}), 400
    if origen_id == destino_id:
        return jsonify({"error": "El origen y el destino son la misma llave."}), 400

    origen = Llave.query.get(origen_id)
    destino = Llave.query.get(destino_id)
    if not origen or _llave_fuera_de_workspace(admin, origen):
        return jsonify({"error": "Llave de origen no encontrada"}), 404
    if not destino or _llave_fuera_de_workspace(admin, destino):
        return jsonify({"error": "Llave de destino no encontrada"}), 404
    if origen.campeonato_id != destino.campeonato_id:
        return jsonify({"error": "Las llaves pertenecen a campeonatos distintos."}), 400
    if origen.tipo_norm != destino.tipo_norm:
        return jsonify({"error": "No se puede mover entre combate y figuras."}), 400
    if origen.estado_norm != "pendiente" or destino.estado_norm != "pendiente":
        return jsonify({
            "error": "Solo se puede mover entre llaves pendientes. Las activas "
                     "o terminadas no se tocan para no perder resultados."
        }), 409

    tipo = origen.tipo_norm
    comp_mover = None
    restantes = []
    for c in (origen.estructura or {}).get("competidores", []):
        if c.get("id") == competidor_id:
            comp_mover = _comp_plano(c)
        else:
            restantes.append(_comp_plano(c))
    if not comp_mover:
        return jsonify({"error": "Competidor no encontrado en la llave de origen"}), 404

    destino_comps = _comps_planos(destino.estructura)
    clave_nuevo = (comp_mover["nombre"].strip().lower(), comp_mover["club"].strip().lower())
    if any(
        (c["nombre"].strip().lower(), c["club"].strip().lower()) == clave_nuevo
        for c in destino_comps
    ):
        return jsonify({
            "error": f"\"{comp_mover['nombre']}\" ya está en la llave de destino."
        }), 409
    destino_comps.append(comp_mover)

    error = _validar_competidores(tipo, destino_comps)
    if error:
        return jsonify({"error": error}), 400

    origen_eliminada = False
    if len(restantes) == 0:
        # Movió al único competidor: la llave origen queda vacía y se elimina.
        db.session.delete(origen)
        origen_eliminada = True
    else:
        error = _validar_competidores(tipo, restantes)
        if error:
            return jsonify({
                "error": f"La llave de origen quedaría inválida: {error} "
                         "Usa «Combinar» para fusionar las llaves completas."
            }), 409
        origen.estructura = _regenerar(tipo, restantes)

    destino.estructura = _regenerar(tipo, destino_comps)
    db.session.commit()

    respuesta = {
        "message": f"\"{comp_mover['nombre']}\" movido a '{destino.nombre}' "
                   "(cuadros re-sorteados)",
        "destino": _con_numero_tatami([destino])[0],
        "origen_eliminada": origen_eliminada,
    }
    if not origen_eliminada:
        respuesta["origen"] = _con_numero_tatami([origen])[0]
    return jsonify(respuesta), 200
