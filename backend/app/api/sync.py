"""
Lo que el ecosistema DINAMYT le PIDE a Campeonatos.

Hasta octubre de 2026 no había nada en este sentido: Campeonatos pregunta al
portal (el pase, la apariencia) y le avisa (`/sync/alta`), pero nadie le
hablaba a él. Lo primero que lo necesitó fue borrar una cuenta.

La puerta es `ECOSYSTEM_SYNC_SECRET`, el mismo secreto con el que esta app ya
firma lo que manda al portal. **Sin esa variable las rutas no existen** (404):
el PC del evento no la lleva, y ahí nadie de fuera tiene por qué entrar.
"""

import hmac
import os
import re
import secrets
from datetime import datetime, timezone

import bcrypt
from flask import Blueprint, jsonify, request

from ..extensions import db
from ..models.asignacion import AccesoTatami
from ..models.campeonato import Campeonato
from ..models.competidor import Competidor, Inscripcion
from ..models.usuario import Usuario
from ..rls import sin_workspace

sync_bp = Blueprint("sync", __name__)

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

#: El nombre que queda donde la persona tiene que seguir constando sin datos.
NOMBRE_BORRADA = "PERSONA ELIMINADA"


def _puerta():
    """`None` si pasa; 404 si este despliegue no tiene canal; 401 si el secreto no es."""
    esperado = os.getenv("ECOSYSTEM_SYNC_SECRET", "").strip()
    if not esperado:
        return 404
    recibido = (request.headers.get("x-dinamyt-sync") or "").strip()
    return None if hmac.compare_digest(recibido.encode(), esperado.encode()) else 401


@sync_bp.route("/supresion", methods=["POST"])
def supresion():
    """
    La cuenta se borró en DINAMYT: lo suyo aquí también.

    El portal lo pide antes de borrar lo suyo y espera: si esto falla, allí no
    se borra nada y lo reintenta al día siguiente. Idempotente.

    · **La cuenta** (`usuarios`) se vacía y se da de baja; no se borra, porque
      de ella cuelgan campeonatos, llaves y asignaciones que son del evento.
      Sus accesos a los tatamis (con la IP) sí se borran.
    · **Su ficha de competidor**: lo que no llegó a competir —inscripciones a
      campeonatos que siguen en preparación— se borra. Si con eso no le queda
      nada, se borra la ficha. Si compitió, la ficha se queda con su nombre y
      su club, sin documento, nacimiento ni peso: los resultados oficiales
      llevan su nombre (decidido el 14 oct 2026), y las llaves y combates ya
      lo guardan copiado.
    """
    cerrada = _puerta()
    if cerrada == 404:
        return jsonify({"error": "No encontrado."}), 404
    if cerrada == 401:
        return jsonify({"error": "Secreto inválido."}), 401

    datos = request.get_json(silent=True) or {}
    eco_sub = str(datos.get("ecoSub") or "").strip()
    if not UUID.match(eco_sub):
        return jsonify({"error": "Falta `ecoSub`."}), 422
    # La llave entre un competidor y una persona (decisión 10): encuentra la
    # ficha que nunca se enlazó a la cuenta.
    documento = str(datos.get("documento") or "").strip() or None

    ahora = datetime.now(timezone.utc)
    with sin_workspace():
        usuarios = Usuario.query.filter(Usuario.eco_sub == eco_sub).all()
        for u in usuarios:
            _vaciar_usuario(u, ahora)

        filtro = Competidor.eco_sub == eco_sub
        if documento:
            filtro = db.or_(
                filtro,
                db.and_(Competidor.documento == documento, Competidor.eco_sub.is_(None)),
            )
        borrados = conservados = 0
        for ficha in Competidor.query.filter(filtro).all():
            if _borrar_o_vaciar_competidor(ficha):
                borrados += 1
            else:
                conservados += 1
        db.session.commit()

    return jsonify(
        {
            "usuarios": len(usuarios),
            "competidoresBorrados": borrados,
            "competidoresConservados": conservados,
        }
    )


def _vaciar_usuario(u, ahora):
    AccesoTatami.query.filter_by(usuario_id=u.id).delete(synchronize_session=False)
    u.nombre = NOMBRE_BORRADA
    u.email = f"eliminado-{u.id}@eliminado.invalid"
    # La columna no admite vacío: un hash de algo que nadie conoce.
    u.password_hash = bcrypt.hashpw(secrets.token_bytes(32), bcrypt.gensalt()).decode("utf-8")
    u.eco_sub = None
    u.club = None
    u._clubes = None
    u.delegacion = None
    u.pais_delegacion = None
    u._roles_del_portal = None
    u.puede_juzgar = False
    u.activo = False
    u.eliminado_at = ahora


def _borrar_o_vaciar_competidor(ficha):
    """`True` si la ficha se borró; `False` si se quedó, vaciada, porque compitió."""
    for ins in Inscripcion.query.filter_by(competidor_id=ficha.id).all():
        camp = db.session.get(Campeonato, ins.campeonato_id)
        if camp is None or camp.estado == "preparacion":
            db.session.delete(ins)
    db.session.flush()

    if Inscripcion.query.filter_by(competidor_id=ficha.id).count() == 0:
        db.session.delete(ficha)
        return True
    ficha.documento = None
    ficha.fecha_nacimiento = None
    ficha.eco_sub = None
    ficha.peso = None
    return False
