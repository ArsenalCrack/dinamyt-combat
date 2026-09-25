"""
Lo que dio el portal, el portal lo quita (nº 5 de la PARTE 4 de
`PLAN-CAMPEONATOS.md`, decidido el 25 de septiembre de 2026).

Hasta aquí la regla era D2: el portal DA papeles al entrar, solo la consola
los QUITA. Eso dejaba a quien le quitaban el papel de juez o de maestro en el
portal con ese papel aquí para siempre. Ahora la regla es por procedencia
(`usuarios.roles_del_portal`), y se aplica al entrar, sin canal nuevo:

  1. Lo que dio el pase y un pase posterior ya no trae → se retira.
  2. Lo que se puso a mano en la consola → no se toca nunca.
  3. `admin` → no se toca nunca.
  4. Un pase del portal viejo (sin la LISTA `roles_campeonatos`) no quita
     nada: solo trae el papel principal, y quitar el resto por eso sería
     degradar a la gente por un pase incompleto.
  5. Quien se queda sin papeles, se queda con `competidor` (su panel).
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jwt  # noqa: E402
import pytest  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

from app import create_app, espejo, identidad  # noqa: E402
from app.config import DevelopmentConfig  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models.usuario import Usuario  # noqa: E402

DevelopmentConfig.SQLALCHEMY_DATABASE_URI = "sqlite://"

LLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
SUB = "aa000000-0000-4000-8000-0000000000d5"
CORREO = "portal@dinamyt.org"


@pytest.fixture()
def cliente(monkeypatch):
    aplicacion = create_app("development")
    aplicacion.config["ECOSYSTEM_JWKS_URL"] = "https://ejemplo.invalid/auth/jwks"
    monkeypatch.setattr(identidad, "_llave_del_pase", lambda token, url: LLAVE.public_key())
    monkeypatch.setattr(espejo, "club_del_pase", lambda claims, pase: None)
    with aplicacion.app_context():
        db.create_all()
        yield aplicacion.test_client()
        db.session.remove()
        db.drop_all()


def entrar(cliente, rol, roles=None):
    """Entra con un pase. `roles=None` es el pase del portal viejo (sin lista)."""
    ahora = int(time.time())
    cuerpo = {
        "sub": SUB, "email": CORREO, "fullName": "Persona Del Portal",
        "iss": identidad.EMISOR_ECOSYSTEM, "iat": ahora, "exp": ahora + 1800,
        "app_scopes": ["campeonatos"], "role_campeonatos": rol,
    }
    if roles is not None:
        cuerpo["roles_campeonatos"] = roles
    token = jwt.encode(cuerpo, LLAVE, algorithm="RS256")
    res = cliente.post("/api/auth/sesion", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200, res.get_json()
    return fila()


def fila():
    db.session.expire_all()
    return Usuario.query.filter_by(email=CORREO).one()


# ══════════════════════════════════════════════════════════════════════════
#  1 · Lo que dio el portal, el portal lo quita
# ══════════════════════════════════════════════════════════════════════════

def test_nace_con_todo_lo_del_pase_como_del_portal(cliente):
    u = entrar(cliente, "maestro", ["maestro", "judge"])
    assert u.roles == ["maestro", "juez"]
    assert u.roles_del_portal == ["maestro", "juez"]


def test_le_quitan_el_juez_en_el_portal_y_aqui_tambien(cliente):
    entrar(cliente, "maestro", ["maestro", "judge"])
    u = entrar(cliente, "maestro", ["maestro"])
    assert u.roles == ["maestro"]
    assert u.puede_juzgar is False
    assert u.roles_del_portal == ["maestro"]


def test_lo_que_se_suma_despues_tambien_es_del_portal(cliente):
    entrar(cliente, "maestro", ["maestro"])
    assert entrar(cliente, "maestro", ["maestro", "judge"]).roles_del_portal == ["maestro", "juez"]
    assert entrar(cliente, "maestro", ["maestro"]).roles == ["maestro"]


def test_sin_ningun_papel_se_queda_en_su_panel(cliente):
    entrar(cliente, "judge", ["judge"])
    u = entrar(cliente, "competitor", ["competitor"])
    assert u.roles == ["competidor"]


# ══════════════════════════════════════════════════════════════════════════
#  2 y 3 · Lo de la consola, y el admin, no se tocan
# ══════════════════════════════════════════════════════════════════════════

def test_lo_puesto_en_la_consola_no_lo_quita_el_portal(cliente):
    u = Usuario(email=CORREO, nombre="PERSONA", rol="maestro", eco_sub=SUB, activo=True)
    u.set_password("secret123")
    u.clubes = ["DOJANG SUR"]
    u.roles = ["maestro", "juez"]  # a mano, como antes de esto: sin procedencia
    db.session.add(u)
    db.session.commit()

    assert entrar(cliente, "maestro", ["maestro"]).roles == ["maestro", "juez"]


def test_lo_que_la_consola_vuelve_a_dar_deja_de_ser_del_portal(cliente):
    u = entrar(cliente, "maestro", ["maestro", "judge"])
    u.fijar_papeles_a_mano(["maestro"])           # la consola lo quita…
    u.fijar_papeles_a_mano(["maestro", "juez"])   # …y lo vuelve a dar
    db.session.commit()
    assert fila().roles_del_portal == ["maestro"]

    assert entrar(cliente, "maestro", ["maestro"]).roles == ["maestro", "juez"]


def test_el_admin_no_lo_quita_nadie_desde_fuera(cliente):
    u = entrar(cliente, "admin", ["admin", "judge"])
    assert u.roles == ["admin", "juez"]
    assert u.roles_del_portal == ["juez"]

    u = entrar(cliente, "judge", ["judge"])
    assert u.roles == ["admin", "juez"]


# ══════════════════════════════════════════════════════════════════════════
#  4 · Un pase incompleto no quita nada
# ══════════════════════════════════════════════════════════════════════════

def test_el_pase_del_portal_viejo_no_quita_nada(cliente):
    entrar(cliente, "maestro", ["maestro", "judge"])
    # Sin `roles_campeonatos`: solo el papel principal. No es «ya no juzga».
    assert entrar(cliente, "maestro").roles == ["maestro", "juez"]


def test_a_quien_esta_desactivado_no_se_le_toca_nada(cliente):
    entrar(cliente, "maestro", ["maestro", "judge"])
    u = fila()
    u.activo = False
    db.session.commit()
    espejo._retirar_lo_que_el_portal_ya_no_da(u, {"roles_campeonatos": ["maestro"]})
    assert u.roles == ["maestro", "juez"]
