"""
API: Tatamis
Gestión de tatamis y asignaciones de jueces. El acceso de los jueces a un
tatami es exclusivamente por asignación del administrador.
"""

import socket

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models.usuario import Usuario
from ..models.tatami import Tatami
from ..models.asignacion import AsignacionJuez
from ..sede import sede_aqui
from .auth import mayusculas
from .scoping import SOLO_PERSONAL, require_personal, es_dueno_campeonato, es_dueno_usuario, usuario_actual

tatamis_bp = Blueprint("tatamis", __name__)


def _tatami_fuera_de_workspace(user, tatami):
    """True si un admin intenta tocar un tatami de un campeonato ajeno."""
    if user is None or user.rol != "admin":
        return False
    return not es_dueno_campeonato(user, tatami.campeonato)

# Máximo 4 jueces de esquina por tatami (más el Juez Central)
ROLES_TATAMI = ("arbitro", "j1", "j2", "j3", "j4")


def _ip_local():
    """IP LAN de esta máquina, para armar URLs que un teléfono pueda abrir.
    El connect() UDP no envía ningún paquete: solo obliga al sistema a elegir
    la interfaz de red de salida (la misma que ven los demás dispositivos)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return None

def _require_admin():
    from .scoping import require_admin
    return require_admin()


@tatamis_bp.route("/campeonato/<int:camp_id>", methods=["GET"])
@jwt_required()
def listar_por_campeonato(camp_id):
    """GET /api/tatamis/campeonato/:camp_id — Lista tatamis de un campeonato."""
    from ..models.campeonato import Campeonato

    user = require_personal()
    if not user:
        return jsonify({"error": SOLO_PERSONAL}), 403
    if user.rol == "admin":
        camp = Campeonato.query.get(camp_id)
        if not camp or not es_dueno_campeonato(user, camp):
            return jsonify({"error": "Campeonato no encontrado"}), 404
    tatamis = Tatami.query.filter_by(campeonato_id=camp_id).order_by(Tatami.numero).all()
    return jsonify([t.to_dict() for t in tatamis]), 200


@tatamis_bp.route("/<int:tatami_id>", methods=["GET"])
@jwt_required()
def obtener(tatami_id):
    """GET /api/tatamis/:id — Obtener tatami con asignaciones."""
    user = require_personal()
    if not user:
        return jsonify({"error": SOLO_PERSONAL}), 403
    tatami = Tatami.query.get_or_404(tatami_id)
    if _tatami_fuera_de_workspace(user, tatami):
        return jsonify({"error": "Tatami no encontrado"}), 404
    data = tatami.to_dict()

    # Incluir asignaciones
    asignaciones = AsignacionJuez.query.filter_by(tatami_id=tatami_id).all()
    data["asignaciones"] = [a.to_dict() for a in asignaciones]

    return jsonify(data), 200


@tatamis_bp.route("/<int:tatami_id>/asignar", methods=["POST"])
@jwt_required()
@sede_aqui
def asignar_juez(tatami_id):
    """
    POST /api/tatamis/:id/asignar
    Body: { "usuario_id": 2, "rol_tatami": "j1" }
    """
    admin = _require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    data = request.get_json()
    if not data or not data.get("usuario_id") or not data.get("rol_tatami"):
        return jsonify({"error": "usuario_id y rol_tatami son requeridos"}), 400

    tatami = Tatami.query.get_or_404(tatami_id)
    if _tatami_fuera_de_workspace(admin, tatami):
        return jsonify({"error": "Tatami no encontrado"}), 404
    user = Usuario.query.get(data["usuario_id"])
    # Un admin solo asigna SUS jueces (los que él creó); superadmin cualquiera.
    if not user or not es_dueno_usuario(admin, user):
        return jsonify({"error": "Usuario no encontrado"}), 404
    # Se puede asignar un juez, o un maestro con permiso de juez (puede_juzgar).
    if not user.activo or not user.puede_ser_juez:
        return jsonify({
            "error": "Solo se pueden asignar jueces activos (o maestros con permiso de juez)"
        }), 400

    ROLES_VALIDOS = ROLES_TATAMI
    rol = data["rol_tatami"]
    if rol not in ROLES_VALIDOS:
        return jsonify({"error": "Rol inválido"}), 400

    # Verificar si ya existe la asignación en ESTE tatami
    existing = AsignacionJuez.query.filter_by(
        usuario_id=user.id, tatami_id=tatami.id
    ).first()

    if not existing:
        # Validación 1: ¿El usuario ya está asignado en OTRO tatami?
        otra_asig = AsignacionJuez.query.filter_by(
            usuario_id=user.id
        ).filter(AsignacionJuez.tatami_id != tatami.id).first()
        if otra_asig:
            otro_tatami = Tatami.query.get(otra_asig.tatami_id)
            num = otro_tatami.numero if otro_tatami else otra_asig.tatami_id
            return jsonify({
                "error": f"Este juez ya está asignado al Tatami {num}. Desasígnelo primero."
            }), 409

        # Validación 2: ¿El rol ya está ocupado en ESTE tatami por otro usuario?
        rol_ocupado = AsignacionJuez.query.filter_by(
            tatami_id=tatami.id, rol_tatami=rol
        ).filter(AsignacionJuez.usuario_id != user.id).first()
        if rol_ocupado:
            return jsonify({
                "error": f"El rol '{rol}' ya está asignado a otro juez en este tatami."
            }), 409

        asignacion = AsignacionJuez(
            usuario_id=user.id,
            tatami_id=tatami.id,
            rol_tatami=rol,
            nombre_display=mayusculas(data.get("nombre_display", user.nombre)),
            asignado_por_id=admin.id,
        )
        db.session.add(asignacion)
    else:
        # Actualizar rol — verificar que el nuevo rol no esté ocupado por alguien más
        if existing.rol_tatami != rol:
            rol_ocupado = AsignacionJuez.query.filter_by(
                tatami_id=tatami.id, rol_tatami=rol
            ).filter(AsignacionJuez.usuario_id != user.id).first()
            if rol_ocupado:
                return jsonify({
                    "error": f"El rol '{rol}' ya está asignado a otro juez en este tatami."
                }), 409
        existing.rol_tatami = rol
        existing.nombre_display = mayusculas(data.get("nombre_display", user.nombre))

    db.session.commit()
    return jsonify({"message": f"Juez asignado como {rol} en tatami {tatami.numero}"}), 200


@tatamis_bp.route("/<int:tatami_id>/desasignar/<int:usuario_id>", methods=["DELETE"])
@jwt_required()
@sede_aqui
def desasignar_juez(tatami_id, usuario_id):
    """DELETE /api/tatamis/:id/desasignar/:usuario_id — Quitar asignación."""
    admin = _require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    tatami = Tatami.query.get_or_404(tatami_id)
    if _tatami_fuera_de_workspace(admin, tatami):
        return jsonify({"error": "Tatami no encontrado"}), 404

    asig = AsignacionJuez.query.filter_by(
        usuario_id=usuario_id, tatami_id=tatami_id
    ).first()
    if not asig:
        return jsonify({"error": "Asignación no encontrada"}), 404

    db.session.delete(asig)
    db.session.commit()
    return jsonify({"message": "Asignación eliminada"}), 200


@tatamis_bp.route("/<int:tatami_id>/acceso-qr/<int:usuario_id>", methods=["POST"])
@jwt_required()
@sede_aqui
def generar_acceso_qr(tatami_id, usuario_id):
    """
    POST /api/tatamis/:id/acceso-qr/:usuario_id — Solo admin.
    Genera un token de acceso directo para el QR de un juez ASIGNADO a este
    tatami: el juez escanea y entra a su rol sin escribir usuario/contraseña.
    El token es el mismo JWT del login (72 h) y viaja en el fragmento (#) de
    la URL, que no queda en logs del servidor.
    """
    admin = _require_admin()
    if not admin:
        return jsonify({"error": "Solo administradores"}), 403

    tatami = Tatami.query.get_or_404(tatami_id)
    if _tatami_fuera_de_workspace(admin, tatami):
        return jsonify({"error": "Tatami no encontrado"}), 404

    asig = AsignacionJuez.query.filter_by(
        usuario_id=usuario_id, tatami_id=tatami_id
    ).first()
    if not asig:
        return jsonify({"error": "Ese juez no está asignado a este tatami"}), 404

    user = Usuario.query.get(usuario_id)
    if not user or not user.activo:
        return jsonify({"error": "Usuario no encontrado o desactivado"}), 404

    from flask_jwt_extended import create_access_token
    token = create_access_token(
        identity=str(user.id),
        additional_claims={
            "rol": user.rol,
            "nombre": user.nombre,
            "email": user.email,
        },
    )
    return jsonify({
        "token": token,
        "tatami_id": tatami_id,
        "rol_tatami": asig.rol_tatami,
        "nombre": user.nombre,
        # Para que el frontend arme la URL del QR con una dirección que un
        # teléfono de la red pueda abrir (localhost no sirve fuera del PC)
        "ip_local": _ip_local(),
    }), 200


@tatamis_bp.route("/mis-tatamis", methods=["GET"])
@jwt_required()
def mis_tatamis():
    """GET /api/tatamis/mis-tatamis — Tatamis asignados al juez actual."""
    uid = get_jwt_identity()
    asignaciones = AsignacionJuez.query.filter_by(usuario_id=int(uid)).all()

    result = []
    for a in asignaciones:
        tatami = Tatami.query.get(a.tatami_id)
        if tatami:
            t_data = tatami.to_dict()
            t_data["mi_rol"] = a.rol_tatami
            t_data["campeonato_nombre"] = tatami.campeonato.nombre if tatami.campeonato else None
            result.append(t_data)

    return jsonify(result), 200
