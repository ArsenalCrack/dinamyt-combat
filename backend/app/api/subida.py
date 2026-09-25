"""
API: la subida automática de resultados (F8 de PLAN-CAMPEONATOS).

Dos rutas, las dos del administrador y las dos para `/admin`:

  · `GET  /api/subida/estado`   — qué está pendiente, qué subió, por qué no.
  · `POST /api/subida/intentar` — el botón «Subir ahora».

La mecánica está en `app/cartero.py`. Aquí solo se decide quién puede y qué se
le cuenta: una cola que nadie ve es una cola que nadie vacía, y ese silencio
es la avería que más caro ha salido en esta app.
"""

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from .. import cartero
from .scoping import require_admin

subida_bp = Blueprint("subida", __name__)

# Por qué no se subió, en una frase que diga qué hacer.
MOTIVOS = {
    "sin_destino": (
        "Esta instalación no tiene a dónde subir: falta CAMPEONATOS_ONLINE_URL en "
        "su configuración, o no empieza por https://. Los resultados se pueden "
        "seguir llevando a mano (Reportes → Exportar resultados).",
        409,
    ),
    "subiendo": (
        "Ya se están subiendo en este momento. En un minuto se actualiza.",
        409,
    ),
    "sin_sesion": (
        "Para subirlos, entra a esta instalación con tu cuenta de DINAMYT (hace "
        "falta internet). Con tu sesión se suben solos.",
        409,
    ),
    "en_combate": (
        "Hay un combate en marcha: se sube cuando termine, para no competir con "
        "el tatami por la red.",
        409,
    ),
}


@subida_bp.route("/estado", methods=["GET"])
@jwt_required()
def estado_de_la_subida():
    if not require_admin():
        return jsonify({"error": "Solo administradores"}), 403
    return jsonify(cartero.estado()), 200


@subida_bp.route("/intentar", methods=["POST"])
@jwt_required()
def intentar_subida():
    if not require_admin():
        return jsonify({"error": "Solo administradores"}), 403
    resultado = cartero.vaciar(forzar=True)
    motivo = resultado.get("motivo")
    if motivo in MOTIVOS:
        texto, codigo = MOTIVOS[motivo]
        return jsonify({**resultado, "error": texto}), codigo
    return jsonify(resultado), 200
