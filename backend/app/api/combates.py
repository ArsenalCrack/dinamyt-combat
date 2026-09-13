"""
API: Combates
Historial y detalle de combates guardados.
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..models.combate import Combate
from ..models.tatami import SesionTatami
from .scoping import SOLO_PERSONAL, require_personal

combates_bp = Blueprint("combates", __name__)


@combates_bp.route("/tatami/<int:tatami_id>", methods=["GET"])
@jwt_required()
def listar_por_tatami(tatami_id):
    """GET /api/combates/tatami/:tatami_id — Combates de un tatami."""
    if not require_personal():
        return jsonify({"error": SOLO_PERSONAL}), 403
    sesiones = SesionTatami.query.filter_by(tatami_id=tatami_id).all()
    sesion_ids = [s.id for s in sesiones]

    combates = (
        Combate.query
        .filter(Combate.sesion_tatami_id.in_(sesion_ids))
        .order_by(Combate.created_at.desc())
        .limit(100)
        .all()
    )

    return jsonify([c.to_dict() for c in combates]), 200


@combates_bp.route("/<int:combate_id>", methods=["GET"])
@jwt_required()
def detalle(combate_id):
    """GET /api/combates/:id — Detalle completo de un combate."""
    if not require_personal():
        return jsonify({"error": SOLO_PERSONAL}), 403
    combate = Combate.query.get_or_404(combate_id)
    return jsonify(combate.to_dict(include_historial=True)), 200


@combates_bp.route("/recientes", methods=["GET"])
@jwt_required()
def recientes():
    """GET /api/combates/recientes — Últimos combates."""
    if not require_personal():
        return jsonify({"error": SOLO_PERSONAL}), 403
    limit = request.args.get("limit", 20, type=int)
    combates = (
        Combate.query
        .order_by(Combate.created_at.desc())
        .limit(min(limit, 100))
        .all()
    )
    return jsonify([c.to_dict() for c in combates]), 200
