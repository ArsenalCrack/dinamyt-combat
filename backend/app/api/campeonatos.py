"""
API: Campeonatos
CRUD para campeonatos — solo Admin.
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from ..extensions import db
from ..security import limitar
from ..models.campeonato import ESTADOS_CAMPEONATO, Campeonato
from ..models.tatami import Tatami
from .auth import mayusculas
from .scoping import (
    SOLO_PERSONAL,
    require_personal,
    es_dueno_campeonato,
    filtrar_campeonatos,
    require_admin as _require_admin,
    usuario_actual,
)

campeonatos_bp = Blueprint("campeonatos", __name__)

# Tope de caracteres de sede/ciudad/país (validado también en el frontend).
CAMPO_LUGAR_MAX = 120

# Tatamis por campeonato: mínimo 1, tope 10 (al crear y al ajustar después).
MIN_TATAMIS = 1
MAX_TATAMIS = 10


def _validar_campo_texto(valor, etiqueta, nombre_propio=False):
    """(texto, error): recorta un campo opcional y valida su longitud.

    `nombre_propio` lo sube a MAYÚSCULAS, como el resto de nombres que escribe
    el admin (ver `mayusculas` en api/auth.py). Se usa en la SEDE, que es un
    nombre a mano libre ("Coliseo El Salitre"). NO en ciudad ni país: esos
    salen de un catálogo (`app/geo.py`) y se comparan contra él por valor
    exacto — "COLOMBIA" dejaría de reconocerse como país válido.
    """
    texto = str(valor or "").strip()
    if not texto:
        return None, None
    if len(texto) > CAMPO_LUGAR_MAX:
        return None, f"{etiqueta} no puede superar {CAMPO_LUGAR_MAX} caracteres."
    return (mayusculas(texto) if nombre_propio else texto), None


@campeonatos_bp.route("", methods=["GET"])
@jwt_required()
def listar():
    """
    GET /api/campeonatos — Lista campeonatos del workspace.
    Superadmin: todos. Admin normal: solo los que él creó.
    """
    user = usuario_actual()
    query = filtrar_campeonatos(user, Campeonato.query)
    campeonatos = query.order_by(Campeonato.created_at.desc()).all()
    return jsonify([c.to_dict() for c in campeonatos]), 200


@campeonatos_bp.route("/publico", methods=["GET"])
@limitar(60, 60, nombre="camp-publico")
def listar_publico():
    """
    GET /api/campeonatos/publico — Campeonatos activos con sus tatamis.
    Sin login: lo usa la pantalla pública para elegir a qué tatami entrar.
    Solo expone datos mínimos (nunca PINs ni asignaciones).
    """
    campeonatos = (
        Campeonato.query.filter_by(activo=True)
        .order_by(Campeonato.created_at.desc())
        .all()
    )
    result = []
    for c in campeonatos:
        tatamis = (
            Tatami.query.filter_by(campeonato_id=c.id, activo=True)
            .order_by(Tatami.numero)
            .all()
        )
        result.append({
            "id": c.id,
            "nombre": c.nombre,
            # Ficha pública: detalles del campeonato (sin PII de competidores).
            "descripcion": c.descripcion,
            "fecha_inicio": c.fecha_inicio.isoformat() if c.fecha_inicio else None,
            "fecha_fin": c.fecha_fin.isoformat() if c.fecha_fin else None,
            "lugar": c.lugar,
            "ciudad": c.ciudad,
            "pais": c.pais,
            "estado": c.estado or "preparacion",
            "tatamis": [{"id": t.id, "numero": t.numero} for t in tatamis],
        })
    return jsonify(result), 200


@campeonatos_bp.route("/<int:camp_id>", methods=["GET"])
@jwt_required()
def obtener(camp_id):
    """GET /api/campeonatos/:id — Obtener un campeonato con tatamis."""
    user = require_personal()
    if not user:
        return jsonify({"error": SOLO_PERSONAL}), 403
    camp = Campeonato.query.get_or_404(camp_id)
    # Un admin solo ve los campeonatos de su workspace (404: no revelar).
    # Los jueces conservan lectura (su flujo no navega por campeonatos).
    if user.rol == "admin" and not es_dueno_campeonato(user, camp):
        return jsonify({"error": "Campeonato no encontrado"}), 404
    return jsonify(camp.to_dict(include_tatamis=True)), 200


@campeonatos_bp.route("", methods=["POST"])
@jwt_required()
def crear():
    """
    POST /api/campeonatos
    Body: { "nombre", "descripcion", "fecha_inicio", "fecha_fin", "num_tatamis": 6 }
    Crea el campeonato y sus tatamis con PINs auto-generados.
    """
    admin = _require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    data = request.get_json()
    if not data or not data.get("nombre"):
        return jsonify({"error": "Nombre del campeonato es requerido"}), 400

    from datetime import date

    lugar, error = _validar_campo_texto(data.get("lugar"), "La sede", nombre_propio=True)
    if error:
        return jsonify({"error": error}), 400
    ciudad, error = _validar_campo_texto(data.get("ciudad"), "La ciudad")
    if error:
        return jsonify({"error": error}), 400
    pais, error = _validar_campo_texto(data.get("pais"), "El país")
    if error:
        return jsonify({"error": error}), 400
    estado = data.get("estado", "preparacion")
    if estado not in ESTADOS_CAMPEONATO:
        return jsonify({"error": "Estado de campeonato inválido"}), 400

    camp = Campeonato(
        # El nombre del campeonato encabeza la pantalla pública, el acta y las
        # llaves impresas: va en mayúsculas como los demás nombres. La
        # descripción no — ahí cabe una frase, no un dato.
        nombre=mayusculas(str(data["nombre"]).strip()),
        descripcion=data.get("descripcion"),
        fecha_inicio=date.fromisoformat(data["fecha_inicio"]) if data.get("fecha_inicio") else None,
        fecha_fin=date.fromisoformat(data["fecha_fin"]) if data.get("fecha_fin") else None,
        lugar=lugar,
        ciudad=ciudad,
        pais=pais,
        estado=estado,
        activo=True,
        created_by=admin.id,
    )
    db.session.add(camp)
    db.session.flush()  # Para obtener el ID

    # Crear tatamis (entre MIN_TATAMIS y MAX_TATAMIS). Después se pueden
    # ajustar mientras el campeonato siga en preparación (ver ajustar_tatamis).
    try:
        num_tatamis = int(data.get("num_tatamis", 6))
    except (TypeError, ValueError):
        num_tatamis = 6
    num_tatamis = max(MIN_TATAMIS, min(MAX_TATAMIS, num_tatamis))
    for i in range(1, num_tatamis + 1):
        tatami = Tatami(
            campeonato_id=camp.id,
            numero=i,
            activo=True,
        )
        db.session.add(tatami)

    db.session.commit()

    return jsonify({
        "message": f"Campeonato '{camp.nombre}' creado con {num_tatamis} tatamis",
        "campeonato": camp.to_dict(include_tatamis=True),
    }), 201


@campeonatos_bp.route("/<int:camp_id>", methods=["PUT"])
@jwt_required()
def actualizar(camp_id):
    """PUT /api/campeonatos/:id — Actualizar campeonato."""
    admin = _require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    camp = Campeonato.query.get_or_404(camp_id)
    if not es_dueno_campeonato(admin, camp):
        return jsonify({"error": "Campeonato no encontrado"}), 404
    data = request.get_json()

    if data.get("nombre"):
        camp.nombre = mayusculas(str(data["nombre"]).strip())
    if "descripcion" in data:
        camp.descripcion = data["descripcion"]
    if "activo" in data:
        camp.activo = data["activo"]
    if data.get("fecha_inicio"):
        from datetime import date
        camp.fecha_inicio = date.fromisoformat(data["fecha_inicio"])
    if data.get("fecha_fin"):
        from datetime import date
        camp.fecha_fin = date.fromisoformat(data["fecha_fin"])
    for campo, etiqueta, propio in (
        ("lugar", "La sede", True), ("ciudad", "La ciudad", False), ("pais", "El país", False),
    ):
        if campo in data:
            valor, error = _validar_campo_texto(data.get(campo), etiqueta, nombre_propio=propio)
            if error:
                return jsonify({"error": error}), 400
            setattr(camp, campo, valor)
    if "estado" in data:
        if data["estado"] not in ESTADOS_CAMPEONATO:
            return jsonify({"error": "Estado de campeonato inválido"}), 400
        camp.estado = data["estado"]

    db.session.commit()
    return jsonify(camp.to_dict()), 200


@campeonatos_bp.route("/<int:camp_id>/tatamis", methods=["PUT"])
@jwt_required()
def ajustar_tatamis(camp_id):
    """
    PUT /api/campeonatos/:id/tatamis
    Body: { "num_tatamis": 8 }

    Cambia cuántos tatamis tiene el campeonato, solo mientras está en
    PREPARACIÓN (una vez en curso, mover tatamis desordenaría el evento).
    Al subir crea los que faltan; al bajar borra los de número más alto, de
    modo que el campeonato queda numerado 1..N sin huecos.

    Bajar SE NIEGA (409) si algún tatami a eliminar tiene llaves asignadas o
    combates guardados: se perderían resultados. Las asignaciones de jueces sí
    se liberan solas (cascada) y se informa cuántas fueron.
    """
    from ..models.combate import Combate
    from ..models.llave import Llave
    from ..models.tatami import SesionTatami

    admin = _require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    camp = Campeonato.query.get_or_404(camp_id)
    if not es_dueno_campeonato(admin, camp):
        return jsonify({"error": "Campeonato no encontrado"}), 404

    if (camp.estado or "preparacion") != "preparacion":
        return jsonify({
            "error": "Los tatamis solo se pueden cambiar mientras el campeonato "
                     "está en preparación."
        }), 409

    data = request.get_json() or {}
    try:
        objetivo = int(data.get("num_tatamis"))
    except (TypeError, ValueError):
        return jsonify({"error": "Indica cuántos tatamis debe tener el campeonato."}), 400
    if not MIN_TATAMIS <= objetivo <= MAX_TATAMIS:
        return jsonify({
            "error": f"El campeonato debe tener entre {MIN_TATAMIS} y "
                     f"{MAX_TATAMIS} tatamis."
        }), 400

    tatamis = (
        Tatami.query.filter_by(campeonato_id=camp.id).order_by(Tatami.numero).all()
    )
    numeros_actuales = {t.numero for t in tatamis}
    sobran = [t for t in tatamis if t.numero > objetivo]

    # Antes de borrar nada: comprobar que ningún tatami que sobra guarda trabajo.
    bloqueos = []
    for tat in sobran:
        motivos = []
        llaves = Llave.query.filter_by(tatami_id=tat.id).count()
        if llaves:
            motivos.append(f"tiene {llaves} llave(s) asignada(s)")
        combates = (
            Combate.query
            .join(SesionTatami, Combate.sesion_tatami_id == SesionTatami.id)
            .filter(SesionTatami.tatami_id == tat.id)
            .count()
        )
        if combates:
            motivos.append(f"tiene {combates} combate(s) guardado(s)")
        if motivos:
            bloqueos.append(f"Tatami {tat.numero} {' y '.join(motivos)}")
    if bloqueos:
        return jsonify({
            "error": "No se puede reducir a "
                     f"{objetivo} tatamis: " + "; ".join(bloqueos)
                     + ". Mueve esas llaves a otro tatami o bórralas primero."
        }), 409

    # Los números se leen ANTES del commit: tras borrar, el objeto expira.
    eliminados = [tat.numero for tat in sobran]
    jueces_liberados = 0
    for tat in sobran:
        jueces_liberados += tat.asignaciones.count()
        db.session.delete(tat)

    creados = []
    for numero in range(1, objetivo + 1):
        if numero in numeros_actuales:
            continue
        db.session.add(Tatami(campeonato_id=camp.id, numero=numero, activo=True))
        creados.append(numero)

    db.session.commit()

    if creados and not eliminados:
        message = f"Se agregaron {len(creados)} tatami(s): ahora hay {objetivo}."
    elif eliminados and not creados:
        message = f"Se quitaron {len(eliminados)} tatami(s): ahora hay {objetivo}."
    elif creados or eliminados:
        message = f"Tatamis actualizados: ahora hay {objetivo}."
    else:
        message = f"El campeonato ya tenía {objetivo} tatami(s)."
    if jueces_liberados:
        message += f" {jueces_liberados} juez(ces) quedaron sin asignación."

    return jsonify({
        "message": message,
        "num_tatamis": objetivo,
        "creados": creados,
        "eliminados": eliminados,
        "jueces_liberados": jueces_liberados,
        "campeonato": camp.to_dict(include_tatamis=True),
    }), 200


@campeonatos_bp.route("/<int:camp_id>", methods=["DELETE"])
@jwt_required()
def eliminar(camp_id):
    """DELETE /api/campeonatos/:id — Eliminar campeonato y tatamis."""
    admin = _require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    camp = Campeonato.query.get_or_404(camp_id)
    if not es_dueno_campeonato(admin, camp):
        return jsonify({"error": "Campeonato no encontrado"}), 404
    # Capturar el nombre ANTES de borrar (tras commit el objeto expira)
    nombre = camp.nombre
    # Las llaves referencian campeonato y tatami: borrarlas primero para
    # no violar llaves foráneas en PostgreSQL (producción).
    from ..models.llave import Llave
    Llave.query.filter_by(campeonato_id=camp.id).delete()
    db.session.delete(camp)
    db.session.commit()
    return jsonify({"message": f"Campeonato '{nombre}' eliminado"}), 200


# ══════════════════════════════════════════════════════════════════
#  Generación automática de llaves
#  (config de categorías → secciones → llaves con sorteo)
# ══════════════════════════════════════════════════════════════════

@campeonatos_bp.route("/<int:camp_id>/config-categorias", methods=["GET"])
@jwt_required()
def obtener_config_categorias(camp_id):
    """
    GET /api/campeonatos/:id/config-categorias
    Config guardada del campeonato o, si aún no hay, la config por defecto.
    """
    from ..engine.secciones_engine import config_categorias_default

    admin = _require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403
    camp = Campeonato.query.get_or_404(camp_id)
    if not es_dueno_campeonato(admin, camp):
        return jsonify({"error": "Campeonato no encontrado"}), 404
    config = camp.config_categorias or config_categorias_default()
    return jsonify({
        "config": config,
        "guardada": camp.config_categorias is not None,
    }), 200


@campeonatos_bp.route("/<int:camp_id>/config-categorias", methods=["PUT"])
@jwt_required()
def guardar_config_categorias(camp_id):
    """
    PUT /api/campeonatos/:id/config-categorias
    Body: { "config": { "modalidades": [ ... ] } }
    Guarda la config de categorías con la que se generan las secciones.
    """
    admin = _require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    camp = Campeonato.query.get_or_404(camp_id)
    if not es_dueno_campeonato(admin, camp):
        return jsonify({"error": "Campeonato no encontrado"}), 404
    data = request.get_json() or {}
    config = data.get("config")
    if not isinstance(config, dict) or not isinstance(config.get("modalidades"), list):
        return jsonify({"error": "Config inválida: falta la lista de modalidades."}), 400
    for m in config["modalidades"]:
        if not isinstance(m, dict) or not str(m.get("nombre", "")).strip():
            return jsonify({"error": "Cada modalidad necesita un nombre."}), 400
        if m.get("tipo_llave") not in ("combate", "figuras"):
            return jsonify({
                "error": f"Modalidad '{m.get('nombre')}': tipo_llave debe ser combate o figuras."
            }), 400

    camp.config_categorias = config
    db.session.commit()
    return jsonify({"message": "Configuración de categorías guardada", "config": config}), 200


def _secciones_con_inscritos(camp):
    """
    Genera las secciones desde la config del campeonato y reparte a cada
    inscrito en la suya. Retorna (secciones_con_lista, avisos). Cada sección
    lleva "competidores": [{inscripcion_id, nombre, club, ...}].
    """
    from ..engine.secciones_engine import (
        calcular_edad, config_categorias_default, emparejar_seccion,
        generar_secciones,
    )
    from ..models.competidor import Inscripcion

    config = camp.config_categorias or config_categorias_default()
    secciones = generar_secciones(config.get("modalidades"))
    for s in secciones:
        s["competidores"] = []

    fecha_ref = camp.fecha_inicio or None
    avisos = []
    # Solo las inscripciones ACEPTADAS entran a secciones/llaves (las
    # pendientes son solicitudes de maestros por revisar).
    inscripciones = camp.inscripciones.filter_by(estado="aceptada").all()
    for ins in inscripciones:
        comp = ins.competidor
        if not comp:
            continue
        modalidades = ins.modalidades or []
        if not modalidades:
            avisos.append(
                f"{comp.nombre_completo}: sin modalidades en la inscripción."
            )
            continue
        edad = calcular_edad(comp.fecha_nacimiento, fecha_ref)
        for modalidad in modalidades:
            seccion = emparejar_seccion(secciones, {
                "modalidad": modalidad,
                "genero": comp.genero,
                "grupo_cinturon": ins.grupo_cinturon_efectivo,
                "edad": edad,
                "peso": ins.peso_efectivo,
            })
            if not seccion:
                faltantes = []
                if edad is None:
                    faltantes.append("fecha de nacimiento")
                if not comp.genero:
                    faltantes.append("género")
                if not ins.grupo_cinturon_efectivo:
                    faltantes.append("grupo de cinturón")
                detalle = (
                    f" (faltan datos: {', '.join(faltantes)})" if faltantes
                    else " (sus datos no encajan en ninguna categoría configurada)"
                )
                avisos.append(
                    f"{comp.nombre_completo}: sin sección para {modalidad}{detalle}."
                )
                continue
            seccion["competidores"].append({
                "inscripcion_id": ins.id,
                "competidor_id": comp.id,
                "nombre": comp.nombre_completo,
                "club": comp.club or "",
                "edad": edad,
                "peso": ins.peso_efectivo,
                "grupo_cinturon": ins.grupo_cinturon_efectivo,
                "especial": bool(comp.categoria_especial),
            })
    return secciones, avisos


@campeonatos_bp.route("/<int:camp_id>/secciones-preview", methods=["GET"])
@jwt_required()
def preview_secciones(camp_id):
    """
    GET /api/campeonatos/:id/secciones-preview
    Vista previa: cómo quedarían repartidos los inscritos en secciones con la
    config actual, qué llaves ya existen y qué competidores quedan por fuera.
    No modifica nada.
    """
    from ..models.llave import Llave

    admin = _require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403
    camp = Campeonato.query.get_or_404(camp_id)
    if not es_dueno_campeonato(admin, camp):
        return jsonify({"error": "Campeonato no encontrado"}), 404
    secciones, avisos = _secciones_con_inscritos(camp)

    existentes = {
        l.seccion_clave: {"llave_id": l.id, "estado": l.estado_norm, "nombre": l.nombre}
        for l in Llave.query.filter(
            Llave.campeonato_id == camp.id, Llave.seccion_clave.isnot(None)
        ).all()
    }
    con_gente = 0
    for s in secciones:
        s["llave_existente"] = existentes.get(s["clave"])
        if s["competidores"]:
            con_gente += 1

    return jsonify({
        "secciones": secciones,
        "avisos": avisos,
        "total_secciones": len(secciones),
        "secciones_con_competidores": con_gente,
        "total_inscripciones": camp.inscripciones.filter_by(estado="aceptada").count(),
    }), 200


@campeonatos_bp.route("/<int:camp_id>/generar-llaves", methods=["POST"])
@jwt_required()
@limitar(10, 60, nombre="generar-llaves")
def generar_llaves_auto(camp_id):
    """
    POST /api/campeonatos/:id/generar-llaves
    Body: {
      "reemplazar"?: bool,        ← re-sortea las llaves auto PENDIENTES
      "asignar_tatamis"?: bool,   ← reparte las llaves entre los tatamis
      "solo_claves"?: [clave...]  ← limita a esas secciones (por defecto todas)
    }
    Crea una llave por cada sección con 2+ competidores. Las llaves creadas a
    mano y las auto ya activas/terminadas nunca se tocan.
    """
    from .llaves import generar_estructura, generar_estructura_figuras
    from ..models.llave import Llave

    admin = _require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    camp = Campeonato.query.get_or_404(camp_id)
    if not es_dueno_campeonato(admin, camp):
        return jsonify({"error": "Campeonato no encontrado"}), 404
    data = request.get_json() or {}
    reemplazar = bool(data.get("reemplazar"))
    asignar_tatamis = bool(data.get("asignar_tatamis"))
    solo_claves = set(data.get("solo_claves") or [])

    secciones, avisos = _secciones_con_inscritos(camp)
    if solo_claves:
        secciones = [s for s in secciones if s["clave"] in solo_claves]

    # Llaves auto existentes de este campeonato, por clave de sección.
    existentes = {
        l.seccion_clave: l
        for l in Llave.query.filter(
            Llave.campeonato_id == camp.id, Llave.seccion_clave.isnot(None)
        ).all()
    }

    tatamis = []
    if asignar_tatamis:
        tatamis = (
            Tatami.query.filter_by(campeonato_id=camp.id, activo=True)
            .order_by(Tatami.numero)
            .all()
        )

    creadas, omitidas = [], []
    idx_tatami = 0
    for s in secciones:
        n = len(s["competidores"])
        if n == 0:
            continue
        if n == 1:
            omitidas.append({
                "clave": s["clave"], "nombre": s["nombre"],
                "motivo": f"Solo 1 competidor ({s['competidores'][0]['nombre']}): "
                          "no alcanza para una llave.",
            })
            continue

        anterior = existentes.get(s["clave"])
        if anterior:
            if anterior.estado_norm != "pendiente":
                omitidas.append({
                    "clave": s["clave"], "nombre": s["nombre"],
                    "motivo": f"Ya tiene una llave {anterior.estado_norm} "
                              "(no se toca para no perder resultados).",
                })
                continue
            if not reemplazar:
                omitidas.append({
                    "clave": s["clave"], "nombre": s["nombre"],
                    "motivo": "Ya tiene una llave pendiente. Usa «re-sortear» "
                              "para regenerarla.",
                })
                continue
            db.session.delete(anterior)

        competidores = [
            {"nombre": c["nombre"], "club": c["club"], "especial": c.get("especial", False)}
            for c in s["competidores"]
        ]
        estructura = (
            generar_estructura_figuras(competidores)
            if s["tipo_llave"] == "figuras"
            else generar_estructura(competidores)
        )
        tatami_id = None
        if tatamis:
            tatami_id = tatamis[idx_tatami % len(tatamis)].id
            idx_tatami += 1

        nombre_llave = (
            s["modalidad"] if s["tipo_llave"] == "figuras" else s["nombre"].upper()
        )
        llave = Llave(
            campeonato_id=camp.id,
            tatami_id=tatami_id,
            tipo=s["tipo_llave"],
            nombre=nombre_llave[:120],
            descripcion=s["nombre"][:500],
            estado="pendiente",
            seccion_clave=s["clave"],
            estructura=estructura,
            created_by=admin.id,
        )
        db.session.add(llave)
        creadas.append({"clave": s["clave"], "nombre": s["nombre"], "competidores": n})

    db.session.commit()
    return jsonify({
        "message": f"{len(creadas)} llave(s) generada(s)"
                   + (f", {len(omitidas)} omitida(s)" if omitidas else ""),
        "creadas": creadas,
        "omitidas": omitidas,
        "avisos": avisos,
    }), 201
