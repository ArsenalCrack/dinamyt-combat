"""
API: Resultados públicos (sin login)

Expone los podios y rankings ya definidos de un campeonato para que el público
—competidores y familias— consulte quién quedó en cada categoría, sin cuenta.

Solo lee campeonatos ACTIVOS (misma visibilidad que la pantalla pública) y solo
resultados ya cerrados:
- Llaves de combate terminadas → podio 1°/2°/3°.
- Categorías de figuras calificadas → ranking completo.
- Combates sueltos (fuera de llave) guardados → ganador.

Cada resultado incluye `participantes` (todos los nombres involucrados) para que
el front permita BUSCAR por nombre: un competidor se encuentra entre cientos.

── Publicar desde el software LOCAL ─────────────────────────────────────────────
La organización trabaja el evento en LOCAL (LAN, fluido). Con `/exportar` baja un
archivo .json con estos mismos resultados y con `/importar` lo sube a la instancia
online, que los guarda como "snapshot" (modelo ResultadoPublicado) y los muestra
junto a los calculados en vivo. Los snapshots llevan id `pub:<uuid>`.
"""

import json
import re
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, Response
from flask_jwt_extended import jwt_required

from ..extensions import db
from ..security import limitar
from ..models.campeonato import Campeonato
from ..models.tatami import Tatami, SesionTatami
from ..models.combate import Combate
from ..models.llave import Llave
from ..models.resultado_publicado import ResultadoPublicado
from ..timeutil import iso_utc
from .auth import mayusculas
from .llaves import podio_llave
from .scoping import require_admin, es_dueno_campeonato

resultados_bp = Blueprint("resultados", __name__)

FORMATO_EXPORT = "dinamyt-resultados"


@resultados_bp.route("/campeonatos", methods=["GET"])
@limitar(60, 60, nombre="resultados-campeonatos")
def listar_campeonatos():
    """
    GET /api/resultados/campeonatos — Campeonatos con resultados para el selector.
    Sin login. Incluye los calculados en vivo (campeonatos activos) y los
    snapshots importados desde el software local.
    """
    campeonatos = (
        Campeonato.query.filter_by(activo=True)
        .order_by(Campeonato.created_at.desc())
        .all()
    )
    publicados = {
        p.export_uuid: p
        for p in ResultadoPublicado.query.order_by(
            ResultadoPublicado.importado_at.desc()
        ).all()
    }
    result = []
    ya_puestos = set()
    for c in campeonatos:
        en_vivo = _contar_resultados(c.id)
        publicado = publicados.get(c.export_uuid) if c.export_uuid else None
        # ── Lo que vuelve del evento tiene que verse ──
        #
        # El camino normal es: se crea aquí, se BAJA al PC del evento, se
        # compite allí y los resultados VUELVEN con el mismo `export_uuid`.
        # Aquí el campeonato sigue activo y sin un solo combate, y antes ganaba
        # siempre el vivo: la lista decía «0 resultados» y los que volvieron no
        # se veían en ninguna parte. Manda el que tiene algo que enseñar.
        if publicado is not None and en_vivo == 0:
            result.append(publicado.to_selector())
            ya_puestos.add(c.export_uuid)
            continue
        if publicado is not None:
            # Los dos tienen resultados: el vivo es el de esta instalación.
            ya_puestos.add(c.export_uuid)
        result.append({
            "id": c.id,
            "nombre": c.nombre,
            "num_resultados": en_vivo,
            "publicado": False,
        })

    # Los snapshots de campeonatos que aquí no existen (o no están activos).
    for uuid_pub, p in publicados.items():
        if uuid_pub not in ya_puestos:
            result.append(p.to_selector())

    return jsonify(result), 200


def _tatami_numeros(camp_id):
    """{tatami_id: numero} de los tatamis del campeonato."""
    return {
        t.id: t.numero
        for t in Tatami.query.filter_by(campeonato_id=camp_id).all()
    }


def _sesion_a_tatami(camp_id):
    """{sesion_id: tatami_id} para mapear combates guardados a su tatami."""
    tatami_ids = [t.id for t in Tatami.query.filter_by(campeonato_id=camp_id).all()]
    if not tatami_ids:
        return {}
    return {
        s.id: s.tatami_id
        for s in SesionTatami.query.filter(
            SesionTatami.tatami_id.in_(tatami_ids)
        ).all()
    }


def _combates_del_campeonato(camp_id):
    """Combates guardados (figuras + sueltos) de todos los tatamis del campeonato."""
    sesion_map = _sesion_a_tatami(camp_id)
    if not sesion_map:
        return [], {}
    combates = (
        Combate.query.filter(Combate.sesion_tatami_id.in_(list(sesion_map.keys())))
        .order_by(Combate.created_at.desc())
        .all()
    )
    return combates, sesion_map


def _contar_resultados(camp_id):
    """Nº aproximado de tarjetas de resultado (para el selector)."""
    llaves = [
        l for l in Llave.query.filter_by(campeonato_id=camp_id).all()
        if l.tipo_norm == "combate" and podio_llave(l.estructura)
    ]
    combates, _ = _combates_del_campeonato(camp_id)
    figuras_o_sueltos = [
        c for c in combates
        if (c.jueces_detalle or {}).get("tipo") == "figuras"
        or not (c.jueces_detalle or {}).get("llave")
    ]
    return len(llaves) + len(figuras_o_sueltos)


def _nombre_categoria(combate):
    detalle = combate.jueces_detalle or {}
    if detalle.get("nombre_categoria"):
        return detalle["nombre_categoria"]
    if combate.categoria and combate.categoria.nombre:
        return combate.categoria.nombre
    return "Combate"


def _construir_resultados(camp_id):
    """Arma la lista de resultados + filtros de un campeonato (lógica en vivo).

    Devuelve {resultados, categorias, tatamis}. Reutilizado por el endpoint
    público en vivo y por la exportación.
    """
    numeros = _tatami_numeros(camp_id)
    resultados = []

    # ── 1) Llaves de combate con podio (terminadas o con campeón) ──
    llaves = Llave.query.filter_by(campeonato_id=camp_id).all()
    for ll in llaves:
        if ll.tipo_norm != "combate":
            continue
        podio = podio_llave(ll.estructura)
        if not podio:
            continue
        comps = (ll.estructura or {}).get("competidores", [])
        resultados.append({
            "tipo": "combate",
            "id": f"llave-{ll.id}",
            "nombre": ll.nombre,
            "descripcion": ll.descripcion or "",
            "tatami_numero": numeros.get(ll.tatami_id),
            "podio": podio,
            "participantes": [c.get("nombre", "") for c in comps if c.get("nombre")],
            "num_competidores": len(comps),
            "fecha": iso_utc(ll.created_at),
        })

    # ── 2) Figuras y combates sueltos (desde los combates guardados) ──
    combates, sesion_map = _combates_del_campeonato(camp_id)
    for c in combates:
        detalle = c.jueces_detalle or {}
        tatami_num = numeros.get(sesion_map.get(c.sesion_tatami_id))
        es_figuras = detalle.get("tipo") == "figuras" or c.ronda_final == "figuras"

        if es_figuras:
            ranking = detalle.get("ranking") if isinstance(detalle.get("ranking"), list) else []
            resultados.append({
                "tipo": "figuras",
                "id": f"comb-{c.id}",
                "nombre": _nombre_categoria(c),
                "descripcion": (detalle.get("descripcion") or "").strip(),
                "tatami_numero": tatami_num,
                "ranking": [
                    {
                        "puesto": r.get("puesto"),
                        "nombre": r.get("nombre", "-"),
                        "club": r.get("club", ""),
                        "total": r.get("total", 0),
                        "especial": bool(r.get("especial")),
                        "empate": bool(r.get("empate")),
                    }
                    for r in ranking
                ],
                "participantes": [r.get("nombre", "") for r in ranking if r.get("nombre")],
                "num_competidores": len(ranking),
                "fecha": iso_utc(c.created_at),
            })
            continue

        # Combate suelto: los que pertenecen a una llave ya se muestran como
        # podio (arriba); aquí solo los combates individuales sin llave.
        if detalle.get("llave"):
            continue
        ganador_color = c.ganador
        ganador_nombre = (
            c.nombre_hong if ganador_color == "hong"
            else c.nombre_chung if ganador_color == "chung"
            else None
        )
        resultados.append({
            "tipo": "combate_suelto",
            "id": f"comb-{c.id}",
            "nombre": _nombre_categoria(c),
            "descripcion": "",
            "tatami_numero": tatami_num,
            "hong": {"nombre": c.nombre_hong, "marcador": c.marcador_hong or 0},
            "chung": {"nombre": c.nombre_chung, "marcador": c.marcador_chung or 0},
            "ganador": {"nombre": ganador_nombre, "color": ganador_color},
            "participantes": [
                n for n in (c.nombre_hong, c.nombre_chung)
                if n and n not in ("Hong", "Chung")
            ],
            "fecha": iso_utc(c.created_at),
        })

    # Listas para los filtros del front
    categorias = sorted({r["nombre"] for r in resultados if r.get("nombre")})
    tatamis = sorted({r["tatami_numero"] for r in resultados if r.get("tatami_numero")})

    return {"resultados": resultados, "categorias": categorias, "tatamis": tatamis}


@resultados_bp.route("/campeonato/<camp_id>", methods=["GET"])
@limitar(60, 60, nombre="resultados-campeonato")
def resultados_campeonato(camp_id):
    """
    GET /api/resultados/campeonato/:id — Resultados públicos del campeonato.
    :id puede ser el id numérico de un campeonato en vivo, o `pub:<uuid>` para
    un snapshot importado. 404 si no existe o (en vivo) no está activo.
    """
    # Snapshot importado
    if isinstance(camp_id, str) and camp_id.startswith("pub:"):
        pub = ResultadoPublicado.query.filter_by(export_uuid=camp_id[4:]).first()
        if not pub:
            return jsonify({"error": "Resultados no encontrados"}), 404
        return jsonify(pub.to_resultados()), 200

    # Campeonato en vivo (id numérico)
    try:
        cid = int(camp_id)
    except (TypeError, ValueError):
        return jsonify({"error": "Campeonato no encontrado"}), 404

    camp = Campeonato.query.get(cid)
    if not camp or not camp.activo:
        return jsonify({"error": "Campeonato no encontrado"}), 404

    data = _construir_resultados(cid)
    # Sin nada en vivo, lo que volvió del evento (ver `listar_campeonatos`): un
    # enlace al id del campeonato no puede quedarse vacío teniendo resultados.
    if not data.get("resultados") and camp.export_uuid:
        pub = ResultadoPublicado.query.filter_by(export_uuid=camp.export_uuid).first()
        if pub is not None:
            return jsonify(pub.to_resultados()), 200
    return jsonify({
        "campeonato": {"id": camp.id, "nombre": camp.nombre},
        **data,
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# Publicar: exportar (en el LOCAL) e importar (en el ONLINE)
# ─────────────────────────────────────────────────────────────────────────────

def _slug(texto, defecto="campeonato"):
    limpio = re.sub(r"[^a-zA-Z0-9._-]+", "-", (texto or "").strip()).strip("-")
    return (limpio or defecto).lower()[:60]


def sobre_de_resultados(camp):
    """El archivo de resultados de un campeonato, tal como viaja a internet.

    Lo usan las dos vueltas: el USB (`exportar_resultados`) y la subida
    automática (`app/cartero.py`, F8). Que sea la MISMA función es lo que
    garantiza que lo que sube solo es exactamente lo que se subiría a mano.
    Genera (una vez) el `export_uuid` del campeonato si no lo tiene.
    """
    if not camp.export_uuid:
        camp.export_uuid = uuid.uuid4().hex
        db.session.commit()

    data = _construir_resultados(camp.id)
    return {
        "formato": FORMATO_EXPORT,
        "version": 1,
        "export_uuid": camp.export_uuid,
        "exportado_at": datetime.now(timezone.utc).isoformat(),
        "campeonato": {"nombre": camp.nombre},
        **data,
    }


@resultados_bp.route("/campeonato/<int:camp_id>/exportar", methods=["GET"])
@jwt_required()
def exportar_resultados(camp_id):
    """
    GET /api/resultados/campeonato/:id/exportar (solo admin dueño)
    Descarga un .json con los resultados del campeonato para publicarlos en la
    instancia online. Genera (una vez) un export_uuid estable en el campeonato.
    """
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    camp = Campeonato.query.get(camp_id)
    if not camp or not es_dueno_campeonato(admin, camp):
        # 404 (no 403) para no revelar campeonatos de otro workspace.
        return jsonify({"error": "Campeonato no encontrado"}), 404

    envelope = sobre_de_resultados(camp)
    cuerpo = json.dumps(envelope, ensure_ascii=False, indent=2)
    filename = f"resultados-{_slug(camp.nombre)}.json"
    return Response(
        cuerpo,
        mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@resultados_bp.route("/importar", methods=["POST"])
@jwt_required()
def importar_resultados():
    """
    POST /api/resultados/importar (solo admin)
    Recibe el .json exportado (multipart `file` o cuerpo JSON) y lo guarda como
    snapshot público. Reimportar el mismo campeonato REEMPLAZA el anterior.
    """
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    # Aceptar archivo subido o cuerpo JSON directo.
    envelope = None
    archivo = request.files.get("file")
    if archivo is not None:
        try:
            envelope = json.loads(archivo.read().decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return jsonify({"error": "El archivo no es un JSON válido"}), 400
    else:
        envelope = request.get_json(silent=True)

    if not isinstance(envelope, dict):
        return jsonify({"error": "No se recibió el archivo de resultados"}), 400
    if envelope.get("formato") != FORMATO_EXPORT:
        return jsonify({
            "error": "El archivo no es un export de resultados de DINAMYT"
        }), 400

    export_uuid = str(envelope.get("export_uuid") or "").strip()
    resultados = envelope.get("resultados")
    if not export_uuid or not isinstance(resultados, list):
        return jsonify({"error": "El archivo de resultados está incompleto"}), 400

    # El nombre del campeonato encabeza la ficha pública de resultados: se
    # normaliza igual que los de aquí, porque el archivo puede venir de una
    # instalación anterior a la regla (ver `mayusculas` en api/auth.py).
    nombre = mayusculas((envelope.get("campeonato") or {}).get("nombre") or "Campeonato")
    payload = {
        "resultados": resultados,
        "categorias": envelope.get("categorias", []),
        "tatamis": envelope.get("tatamis", []),
    }

    # ── Reemplazar vale para quien lo publicó, no para quien tenga el archivo ──
    #
    # Se busca con la red levantada: en PostgreSQL, RLS le escondía a otro
    # admin el snapshot ajeno, así que esto no lo veía, intentaba crearlo y
    # chocaba con el `export_uuid` único (un 500). Y en SQLite, sin RLS, lo
    # PISABA: cualquier admin con el archivo reemplazaba lo publicado por otro.
    from ..rls import sin_workspace

    with sin_workspace():
        previo = ResultadoPublicado.query.filter_by(export_uuid=export_uuid).first()
        ajeno = previo is not None and not (
            admin.es_super or previo.created_by == admin.id
        )
    if ajeno:
        return jsonify({
            "error": "Estos resultados los publicó otro administrador. Pídele que "
                     "los actualice, o que los quite para poder publicarlos tú.",
            "motivo": "publicado_por_otro",
        }), 409

    # ── Y el campeonato vivo de ese `export_uuid`, también ──
    #
    # Desde F8 lo que vuelve del evento SE MUESTRA en lugar del campeonato vivo
    # que no tiene combates (`listar_campeonatos`). Sin esta puerta, cualquier
    # admin con el `export_uuid` —viaja en el paquete que se baja al PC del
    # evento— publicaría resultados que se verían como los de un campeonato
    # ajeno. Solo sube resultados a un campeonato quien es su dueño.
    with sin_workspace():
        vivo = Campeonato.query.filter_by(export_uuid=export_uuid).first()
        vivo_ajeno = vivo is not None and not es_dueno_campeonato(admin, vivo)
    if vivo_ajeno:
        return jsonify({
            "error": "Estos resultados son de un campeonato de otro administrador. "
                     "Tiene que subirlos quien lo organiza.",
            "motivo": "campeonato_de_otro",
        }), 409

    pub = ResultadoPublicado.query.filter_by(export_uuid=export_uuid).first()
    nuevo = pub is None
    if nuevo:
        pub = ResultadoPublicado(export_uuid=export_uuid, created_by=admin.id)
        db.session.add(pub)
    pub.nombre = nombre
    pub.payload = payload
    pub.exportado_at = envelope.get("exportado_at")
    pub.importado_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({
        "message": (
            f"Resultados de '{nombre}' importados"
            if nuevo else f"Resultados de '{nombre}' actualizados"
        ),
        "nombre": nombre,
        "num_resultados": len(resultados),
        "nuevo": nuevo,
    }), 200


@resultados_bp.route("/publicado/<export_uuid>", methods=["DELETE"])
@jwt_required()
def eliminar_publicado(export_uuid):
    """
    DELETE /api/resultados/publicado/:uuid (admin dueño o superadmin)
    Quita un snapshot importado de la lista pública.
    """
    admin = require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    pub = ResultadoPublicado.query.filter_by(export_uuid=export_uuid).first()
    if not pub:
        return jsonify({"error": "Resultados no encontrados"}), 404
    if not (admin.es_super or pub.created_by == admin.id):
        return jsonify({"error": "Resultados no encontrados"}), 404

    db.session.delete(pub)
    db.session.commit()
    return jsonify({"message": "Snapshot eliminado"}), 200
