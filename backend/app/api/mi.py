"""
API: el panel del competidor — `/api/mi/*` (F3 de `PLAN-CAMPEONATOS.md`, parte 3).

Es lo único de Campeonatos que es de UNA persona y no de un campeonato. Tres
reglas lo sostienen, y viven aquí para no repetirlas en cada ruta:

  · **Siempre por el `eco_sub` de la sesión, nunca por un id del cliente.** La
    fila la creó un pase firmado por el ecosistema, y ese `sub` es lo único que
    dice quién es. Una ficha es «tuya» cuando `competidores.eco_sub` es tu
    `sub`, y eso solo lo escriben tres caminos: reclamarla aquí con documento y
    fecha de nacimiento, el administrador desde `/admin/competidores`, o el
    paquete que viaja entre instalaciones (F6-c).
  · **Sin `eco_sub` no hay nada que enseñar.** Un usuario creado a mano en el
    modo local no viene del portal y no tiene cuenta a la que colgar una ficha.
  · **Sin la red de RLS, a propósito** (`rls.sin_workspace`). Lo que filtra
    aquí es la persona, no el workspace: un maestro que además compite tiene su
    ficha en el de OTRO administrador, y con la red puesta su propio panel le
    saldría vacío en PostgreSQL.

── De dónde salen los resultados (la opción B del plan) ─────────────────────

La parte 2 dejó el `competidor_uid` en las llaves generadas desde el 13 de
septiembre de 2026. Lo anterior, las llaves hechas a mano, los combates sueltos
y los resultados importados desde el modo local solo tienen nombre (y club).
Lo enlazado se enseña como exacto; lo demás se busca por nombre y sale
**«sin confirmar»**.

Y se busca SOLO en los campeonatos donde alguna ficha tuya está inscrita.
Buscar por nombre en todos sería colgarte los podios de un homónimo de otra
liga, que es justo lo que «sin confirmar» no puede tapar.
"""

import logging
import unicodedata
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from ..extensions import db
from ..models.campeonato import Campeonato
from ..models.competidor import Competidor, Inscripcion, _origen_del_alumno
from ..models.llave import Llave
from ..models.resultado_publicado import ResultadoPublicado
from ..rls import sin_workspace
from ..security import intento_bloqueado, limpiar_intentos, segundos_restantes
from ..timeutil import iso_utc
from .competidores import _validar_documento
from .llaves import podio_llave
from .resultados import _combates_del_campeonato, _nombre_categoria
from .scoping import usuario_actual

log = logging.getLogger(__name__)

mi_bp = Blueprint("mi", __name__)

# Reclamar una ficha que no es tuya es adivinar dos datos de otra persona. El
# tope por usuario es lo que lo vuelve impracticable, y cinco intentos cada
# quince minutos le sobran a quien se equivoca tecleando su propio documento.
RECLAMAR_MAX = 5
RECLAMAR_VENTANA_SEG = 15 * 60

# Una sola respuesta para «no existe» y para «existe pero la fecha no cuadra»:
# distinguirlas le diría a cualquiera qué documentos están registrados.
NO_ENCONTRADA = (
    "No encontramos ninguna ficha con ese documento y esa fecha de nacimiento. "
    "Si compites y no aparece, pídele al administrador del campeonato que la "
    "enlace con tu cuenta."
)

MEDALLAS = {1: "oro", 2: "plata", 3: "bronce"}


# ── Quién eres ───────────────────────────────────────────────────────────────

def _yo():
    """La fila de la sesión, si está activa."""
    user = usuario_actual()
    return user if user is not None and user.activo else None


def _sub(user):
    return str(user.eco_sub or "").strip()


def _clave(texto):
    """Para comparar nombres: sin tildes, sin mayúsculas y sin espacios de más."""
    plano = "".join(
        c for c in unicodedata.normalize("NFD", str(texto or ""))
        if unicodedata.category(c) != "Mn"
    )
    return " ".join(plano.split()).casefold()


class _Quien:
    """Decide si un competidor de una llave o de un ranking eres tú, y con qué certeza."""

    def __init__(self, fichas):
        self.uids = {f.uid for f in fichas if f.uid}
        self.nombres = {(_clave(f.nombre_completo), _clave(f.club)) for f in fichas}

    def es(self, comp):
        """`"confirmado"`, `"sin_confirmar"` o `None`."""
        if not isinstance(comp, dict):
            return None
        uid = comp.get("competidor_uid")
        if uid:
            # Con enlace manda el enlace: si es el de OTRA ficha, no eres tú
            # aunque se llame igual. Es el homónimo que la opción B separa.
            return "confirmado" if uid in self.uids else None
        if self.por_nombre(comp.get("nombre"), comp.get("club")):
            return "sin_confirmar"
        return None

    def por_nombre(self, nombre, club=None):
        """Mismo nombre y, si los dos lados tienen club, mismo club."""
        buscado = _clave(nombre)
        if not buscado:
            return False
        club_buscado = _clave(club)
        return any(
            buscado == mi_nombre
            and (not club_buscado or not mi_club or club_buscado == mi_club)
            for mi_nombre, mi_club in self.nombres
        )


def _fichas_de(user):
    sub = _sub(user)
    if not sub:
        return []
    return (
        Competidor.query.filter(Competidor.eco_sub == sub)
        .order_by(Competidor.created_at.asc())
        .all()
    )


# ── Cómo se enseña cada cosa ─────────────────────────────────────────────────

def _ficha(c):
    # Son los datos de la propia persona: aquí sí viajan documento y fecha.
    return {
        "uid": c.uid,
        "nombre_completo": c.nombre_completo,
        "documento": c.documento,
        "fecha_nacimiento": c.fecha_nacimiento.isoformat() if c.fecha_nacimiento else None,
        "genero": c.genero,
        "cinturon": c.cinturon,
        "grupo_cinturon": c.grupo_cinturon,
        "club": c.club,
    }


def _campeonato_corto(camp):
    return {
        "id": camp.id,
        "nombre": camp.nombre,
        "fecha_inicio": camp.fecha_inicio.isoformat() if camp.fecha_inicio else None,
        "fecha_fin": camp.fecha_fin.isoformat() if camp.fecha_fin else None,
        "lugar": camp.lugar,
        "ciudad": camp.ciudad,
        "pais": camp.pais,
        "estado": camp.estado or "preparacion",
    }


def _maestro_de(ins):
    """Quién te inscribió, si fue un maestro. El admin no es «tu maestro»."""
    autor = ins.autor
    if autor is None or autor.rol != "maestro":
        return None
    return {
        "nombre": autor.nombre,
        "club": _origen_del_alumno(autor, ins.competidor)["club"],
    }


def _inscripcion(ins, camp):
    return {
        "id": ins.id,
        "estado": ins.estado or "aceptada",
        "motivo_rechazo": ins.motivo_rechazo,
        "modalidades": ins.modalidades or [],
        "grupo_cinturon": ins.grupo_cinturon_efectivo,
        "peso": ins.peso_efectivo,
        "ficha": ins.competidor.nombre_completo if ins.competidor else None,
        "maestro": _maestro_de(ins),
        "campeonato": _campeonato_corto(camp),
        "created_at": iso_utc(ins.created_at),
    }


def _es_proximo(camp, hoy):
    """Todavía no ha terminado. Sin fechas cuenta como próximo: aún no se sabe."""
    if (camp.estado or "preparacion") == "finalizado":
        return False
    fin = camp.fecha_fin or camp.fecha_inicio
    return fin is None or fin >= hoy


# ── Los resultados ───────────────────────────────────────────────────────────

def _peleas_de_la_llave(estructura, quien):
    """Cada combate DISPUTADO de una llave en el que estás, y si lo ganaste.

    Un pase directo (un solo competidor en el partido) no es un combate: no se
    cuenta ni como victoria ni como derrota.
    """
    partidos = [p for ronda in (estructura.get("rondas") or []) for p in (ronda or [])]
    if isinstance(estructura.get("bronce"), dict):
        partidos.append(estructura["bronce"])

    peleas = []
    for partido in partidos:
        if not isinstance(partido, dict) or partido.get("ganador") not in (1, 2):
            continue
        uno, dos = partido.get("comp1"), partido.get("comp2")
        if not uno or not dos:
            continue
        for lado, comp in ((1, uno), (2, dos)):
            certeza = quien.es(comp)
            if certeza:
                peleas.append({
                    "gano": partido["ganador"] == lado,
                    "confirmado": certeza == "confirmado",
                })
    return peleas


def _resultados_en(camp, quien):
    """`(resultados, peleas)` de UN campeonato para esta persona.

    Primero lo calculado en vivo. Si ahí no hay nada y existen resultados
    importados del modo local con el mismo `export_uuid`, se miran esos: es el
    caso del 9 de octubre, en que se compite en el PC del evento y lo que llega
    a internet es el archivo de resultados — solo con nombres, hasta F8.
    """
    resultados, peleas, vistos = [], [], set()

    def anotar(tipo, categoria, puesto, certeza, especial=False):
        try:
            puesto = int(puesto)
        except (TypeError, ValueError):
            return
        # Una categoría de figuras guardada dos veces es el mismo resultado.
        clave = (tipo, categoria, puesto)
        if clave in vistos:
            return
        vistos.add(clave)
        resultados.append({
            "campeonato": _campeonato_corto(camp),
            "tipo": tipo,
            "categoria": categoria or "",
            "puesto": puesto,
            "medalla": MEDALLAS.get(puesto),
            "especial": especial,
            "confirmado": certeza == "confirmado",
        })

    for llave in Llave.query.filter_by(campeonato_id=camp.id).all():
        if llave.tipo_norm != "combate":
            continue
        estructura = llave.estructura or {}
        for puesto in podio_llave(estructura, con_uid=True):
            certeza = quien.es(puesto)
            if certeza:
                anotar("combate", llave.nombre, puesto["puesto"], certeza)
        peleas += _peleas_de_la_llave(estructura, quien)

    combates, _ = _combates_del_campeonato(camp.id)
    for c in combates:
        detalle = c.jueces_detalle or {}
        if detalle.get("tipo") == "figuras" or c.ronda_final == "figuras":
            ranking = detalle.get("ranking") if isinstance(detalle.get("ranking"), list) else []
            for fila in ranking:
                certeza = quien.es(fila)
                if certeza:
                    anotar("figuras", _nombre_categoria(c), fila.get("puesto"),
                           certeza, bool(fila.get("especial")))
            continue
        # Combate suelto: solo hay dos nombres, sin club ni enlace.
        if detalle.get("llave") or c.ganador not in ("hong", "chung"):
            continue
        for color, nombre in (("hong", c.nombre_hong), ("chung", c.nombre_chung)):
            if nombre not in ("Hong", "Chung") and quien.por_nombre(nombre):
                peleas.append({"gano": c.ganador == color, "confirmado": False})

    if not resultados and not peleas and camp.export_uuid:
        publicado = ResultadoPublicado.query.filter_by(export_uuid=camp.export_uuid).first()
        for r in ((publicado.payload or {}).get("resultados") or []) if publicado else []:
            if not isinstance(r, dict):
                continue
            tipo = r.get("tipo")
            filas = r.get("podio") if tipo == "combate" else r.get("ranking") if tipo == "figuras" else None
            for fila in filas or []:
                certeza = quien.es(fila)
                if certeza:
                    anotar(tipo, r.get("nombre"), fila.get("puesto"), certeza,
                           bool(fila.get("especial")))

    return resultados, peleas


def _anio(camp):
    cuando = camp.get("fecha_inicio") or ""
    return cuando[:4] or None


def _estadisticas(resultados, peleas):
    medallas = {"oro": 0, "plata": 0, "bronce": 0}
    por_anio, por_modalidad = {}, {}
    for r in resultados:
        medalla = r["medalla"]
        if not medalla:
            continue
        medallas[medalla] += 1
        anio = _anio(r["campeonato"]) or "—"
        por_anio.setdefault(anio, {"oro": 0, "plata": 0, "bronce": 0})[medalla] += 1
        por_modalidad.setdefault(r["tipo"], {"oro": 0, "plata": 0, "bronce": 0})[medalla] += 1

    victorias = sum(1 for p in peleas if p["gano"])
    return {
        "combates": len(peleas),
        "victorias": victorias,
        "derrotas": len(peleas) - victorias,
        "medallas": medallas,
        "por_anio": [{"anio": a, **m} for a, m in sorted(por_anio.items(), reverse=True)],
        "por_modalidad": [{"tipo": t, **m} for t, m in sorted(por_modalidad.items())],
        # Cuánto de todo lo anterior salió por nombre. La pantalla lo dice.
        "sin_confirmar": (
            sum(1 for r in resultados if not r["confirmado"])
            + sum(1 for p in peleas if not p["confirmado"])
        ),
    }


# ── Rutas ────────────────────────────────────────────────────────────────────

@mi_bp.route("/panel", methods=["GET"])
@jwt_required()
def panel():
    """
    GET /api/mi/panel — Todo el panel del competidor en una sola petición.

    {persona, fichas, maestro, inscripciones, proximos, resultados, estadisticas}

    Sin fichas enlazadas responde lo mismo con las listas vacías: la pantalla
    ofrece entonces reclamar la ficha.
    """
    user = _yo()
    if user is None:
        return jsonify({"error": "Usuario no válido"}), 401

    with sin_workspace():
        fichas = _fichas_de(user)
        ids = [f.id for f in fichas]
        inscripciones = (
            Inscripcion.query.filter(Inscripcion.competidor_id.in_(ids))
            .order_by(Inscripcion.created_at.desc())
            .all()
            if ids else []
        )
        ids_camps = {i.campeonato_id for i in inscripciones}
        camps = (
            {c.id: c for c in Campeonato.query.filter(Campeonato.id.in_(ids_camps)).all()}
            if ids_camps else {}
        )

        quien = _Quien(fichas)
        resultados, peleas = [], []
        for camp in camps.values():
            de_aqui, peleas_de_aqui = _resultados_en(camp, quien)
            resultados += de_aqui
            peleas += peleas_de_aqui
        resultados.sort(
            key=lambda r: (r["campeonato"]["fecha_inicio"] or "", r["campeonato"]["id"]),
            reverse=True,
        )

        hoy = date.today()
        vistas = [_inscripcion(i, camps[i.campeonato_id]) for i in inscripciones
                  if i.campeonato_id in camps]
        proximos = {}
        for ins in inscripciones:
            camp = camps.get(ins.campeonato_id)
            if camp and ins.estado != "rechazada" and _es_proximo(camp, hoy):
                proximos[camp.id] = _campeonato_corto(camp)

        cuerpo = {
            "persona": {
                "nombre": user.nombre,
                "email": user.email,
                "roles": user.roles,
                # Sin cuenta de DINAMYT no hay nada que reclamar: la pantalla
                # lo dice en vez de ofrecer un formulario que siempre fallaría.
                "con_cuenta": bool(_sub(user)),
            },
            "fichas": [_ficha(f) for f in fichas],
            # El de la inscripción más reciente hecha por un maestro.
            "maestro": next((v["maestro"] for v in vistas if v["maestro"]), None),
            "inscripciones": vistas,
            "proximos": sorted(
                proximos.values(), key=lambda c: (c["fecha_inicio"] is None, c["fecha_inicio"] or "")
            ),
            "resultados": resultados,
            "estadisticas": _estadisticas(resultados, peleas),
        }
    return jsonify(cuerpo), 200


@mi_bp.route("/ficha/reclamar", methods=["POST"])
@jwt_required()
def reclamar_ficha():
    """
    POST /api/mi/ficha/reclamar — Engancha tu cuenta a TU ficha de atleta.
    Body: { "documento": "...", "fecha_nacimiento": "AAAA-MM-DD" }

    Es la promesa de D5: la ficha existe antes que la cuenta. Quien compitió sin
    DINAMYT —un atleta independiente, o alguien de un club que llegó tarde— la
    reclama con los dos datos que solo él sabe de sí mismo, y su historial
    aparece entero.

    ── Lo que no hace ──
    · **No pisa un enlace.** Si esa ficha ya es de OTRA cuenta, 409 y que lo
      mire una persona: la misma prudencia que `resolver_espejo` con
      `correo_ocupado`.
    · **No reclama sin fecha de nacimiento.** Con solo el documento bastaría
      con conocer la cédula de alguien. Esa ficha la enlaza el administrador.
    """
    user = _yo()
    if user is None:
        return jsonify({"error": "Usuario no válido"}), 401
    sub = _sub(user)
    if not sub:
        return jsonify({
            "error": "Tu usuario no viene de una cuenta de DINAMYT: no hay a "
                     "quién enlazar la ficha.",
            "motivo": "sin_cuenta",
        }), 409

    data = request.get_json(silent=True) or {}
    documento, error = _validar_documento(data.get("documento"))
    try:
        nacimiento = date.fromisoformat(str(data.get("fecha_nacimiento") or ""))
    except ValueError:
        nacimiento = None
    if error or not documento or not nacimiento:
        return jsonify({
            "error": error or "Escribe tu documento y tu fecha de nacimiento."
        }), 400

    # El tope va DESPUÉS de validar el formato —un dedazo no gasta intentos— y
    # ANTES de mirar la base: lo que se limita es preguntar.
    clave = f"reclamar-ficha:{user.id}"
    if intento_bloqueado(clave, RECLAMAR_MAX, RECLAMAR_VENTANA_SEG):
        minutos = max(segundos_restantes(clave) // 60, 1)
        return jsonify({
            "error": f"Demasiados intentos. Vuelve a probar en {minutos} minuto(s)."
        }), 429

    with sin_workspace():
        ficha = Competidor.query.filter_by(documento=documento).first()
        if ficha is None or ficha.fecha_nacimiento is None or ficha.fecha_nacimiento != nacimiento:
            return jsonify({"error": NO_ENCONTRADA}), 404

        if ficha.eco_sub and ficha.eco_sub != sub:
            log.warning(
                "[mi] %s intentó reclamar la ficha %s, enlazada a otra cuenta.",
                user.email, ficha.uid,
            )
            return jsonify({
                "error": "Esa ficha ya está enlazada a otra cuenta de DINAMYT. "
                         "Escribe al administrador del campeonato para que lo revise.",
                "motivo": "ficha_ocupada",
            }), 409

        limpiar_intentos(clave)
        if ficha.eco_sub != sub:
            ficha.eco_sub = sub
            # Quien reclama una ficha compite, aunque su pase no lo dijera (un
            # juez que también compite). Salvo que la consola se lo quitara.
            if not user.tiene_rol("competidor") and "competidor" not in user.roles_quitados:
                user.roles = [*user.roles, "competidor"]
            db.session.commit()
            log.info("[mi] %s reclamó su ficha %s.", user.email, ficha.uid)

        return jsonify({
            "message": "Ficha enlazada con tu cuenta.",
            "ficha": _ficha(ficha),
        }), 200
