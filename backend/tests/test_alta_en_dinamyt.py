"""
El alta de jueces nace en DINAMYT (nº 5 de la PARTE 4 de `PLAN-CAMPEONATOS.md`,
decidido el 25 de septiembre de 2026).

`POST /api/auth/register` creaba una cuenta de AQUÍ con la contraseña que ponía
el admin: una identidad que DINAMYT no conoce y que el pase no puede cortar.
Ahora, con el puente entero (API del ecosistema + `ECOSYSTEM_SYNC_SECRET`):

  1. La cuenta nace en DINAMYT (`POST /sync/alta`, `app: campeonatos`) y el
     espejo nace enlazado, sin contraseña que valga. Solo jueces.
  2. Si DINAMYT dice que no, aquí no se crea nada y el admin lee por qué.
  3. A una cuenta de DINAMYT no se le pone contraseña desde la consola.
  4. **Sin el puente todo sigue como siempre** — y en particular en el PC del
     evento, que desde F8 lleva `ECOSYSTEM_JWKS_URL` pero no el secreto: ahí
     el día del campeonato se tienen que poder crear jueces sin internet.
"""

import io
import json
import sys
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import create_app, espejo  # noqa: E402
from app.api import auth as auth_api  # noqa: E402
from app.config import DevelopmentConfig  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models.usuario import Usuario  # noqa: E402

DevelopmentConfig.SQLALCHEMY_DATABASE_URI = "sqlite://"

JWKS = "https://id.ejemplo.invalid/auth/jwks"
ORG = "0f000000-0000-4000-8000-00000000fede"
SUB_ADMIN = "aa000000-0000-4000-8000-0000000000ad"
SUB_JUEZ = "aa000000-0000-4000-8000-00000000000a"


@pytest.fixture()
def instalacion(monkeypatch):
    monkeypatch.delenv("ECOSYSTEM_SYNC_SECRET", raising=False)
    monkeypatch.delenv("CAMPEONATOS_ONLINE_URL", raising=False)
    aplicacion = create_app("development")
    with aplicacion.app_context():
        db.create_all()
        admin = Usuario(email="admin@fede.org", nombre="ADMIN FEDE", rol="admin",
                        activo=True, eco_sub=SUB_ADMIN, org_id=ORG, org_nombre="FEDE")
        admin.set_password("secret123")
        db.session.add(admin)
        db.session.commit()

        from flask_jwt_extended import create_access_token

        token = create_access_token(identity=str(admin.id), additional_claims={"rol": "admin"})
        yield aplicacion, aplicacion.test_client(), {"Authorization": f"Bearer {token}"}, admin
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def con_puente(instalacion, monkeypatch):
    """La instalación de internet: pase y espejo."""
    aplicacion, cliente, cabecera, admin = instalacion
    aplicacion.config["ECOSYSTEM_JWKS_URL"] = JWKS
    monkeypatch.setenv("ECOSYSTEM_SYNC_SECRET", "secreto-del-espejo")
    llamadas = []

    def alta_falsa(email, nombre, org_id, invitado_por=None):
        llamadas.append((email, nombre, org_id, invitado_por))
        return {
            "ecoSub": SUB_JUEZ,
            "cuenta": "nueva",
            "invitacion": {"enviadaPorCorreo": False, "enlace": "https://dinamyt.org/poner-contrasena?token=x",
                           "venceEnDias": 7},
        }

    monkeypatch.setattr(auth_api, "alta_de_juez_en_dinamyt", alta_falsa)
    return cliente, cabecera, admin, llamadas


def _alta(cliente, cabecera, **cuerpo):
    datos = {"email": "juez@nuevo.org", "nombre": "Juez Nuevo", "rol": "juez"}
    datos.update(cuerpo)
    return cliente.post("/api/auth/register", headers=cabecera, json=datos)


# ══════════════════════════════════════════════════════════════════════════
#  1 · Con el puente, el juez nace en DINAMYT
# ══════════════════════════════════════════════════════════════════════════

def test_la_consola_sabe_que_formulario_ensenar(con_puente):
    cliente, cabecera, _, _ = con_puente
    assert cliente.get("/api/auth/alta", headers=cabecera).get_json() == {"en_dinamyt": True}


def test_el_juez_nace_en_dinamyt_y_el_espejo_enlazado(con_puente):
    cliente, cabecera, admin, llamadas = con_puente

    r = _alta(cliente, cabecera, password="la-ignora")

    assert r.status_code == 201, r.get_json()
    assert llamadas == [("juez@nuevo.org", "JUEZ NUEVO", ORG, SUB_ADMIN)]
    cuerpo = r.get_json()
    assert cuerpo["cuenta"] == "nueva"
    assert cuerpo["invitacion"]["enlace"].startswith("https://dinamyt.org/poner-contrasena")

    juez = Usuario.query.filter_by(email="juez@nuevo.org").one()
    assert str(juez.eco_sub) == SUB_JUEZ
    assert juez.roles == ["juez"]
    assert juez.roles_del_portal == ["juez"]
    assert juez.org_id == ORG
    assert juez.creado_por_id == admin.id
    # La contraseña que mandó el formulario no vale: aquí se entra con el pase.
    assert not juez.check_password("la-ignora")


@pytest.mark.parametrize("rol, texto", [
    ("maestro", "Clubes invitados"),
    ("admin", "se crean en DINAMYT"),
])
def test_ni_maestros_ni_administradores(con_puente, rol, texto):
    cliente, cabecera, _, llamadas = con_puente
    r = _alta(cliente, cabecera, rol=rol, clubes=["DOJANG SUR"], password="secret123")
    assert r.status_code == 400
    assert texto in r.get_json()["error"]
    assert llamadas == []
    assert Usuario.query.filter_by(email="juez@nuevo.org").first() is None


def test_sin_organizacion_conocida_no_se_adivina(con_puente):
    cliente, cabecera, admin, llamadas = con_puente
    admin.org_id = None
    db.session.commit()

    r = _alta(cliente, cabecera)

    assert r.status_code == 409
    assert r.get_json()["motivo"] == "sin_organizacion"
    assert llamadas == []


def test_un_correo_que_ya_esta_aqui_no_llega_a_dinamyt(con_puente):
    cliente, cabecera, _, llamadas = con_puente
    assert _alta(cliente, cabecera, email="admin@fede.org").status_code == 409
    assert llamadas == []


def test_una_cuenta_de_dinamyt_que_ya_tiene_espejo_con_otro_correo(con_puente):
    cliente, cabecera, _, _ = con_puente
    viejo = Usuario(email="otro@correo.org", nombre="JUEZ", rol="juez", activo=True, eco_sub=SUB_JUEZ)
    viejo.set_password("secret123")
    db.session.add(viejo)
    db.session.commit()

    r = _alta(cliente, cabecera)

    assert r.status_code == 409
    assert "otro@correo.org" in r.get_json()["error"]


# ══════════════════════════════════════════════════════════════════════════
#  2 · Si DINAMYT dice que no, aquí no nace nada
# ══════════════════════════════════════════════════════════════════════════

def test_el_no_de_dinamyt_llega_tal_cual_y_no_crea_nada(con_puente, monkeypatch):
    cliente, cabecera, _, _ = con_puente

    def rechaza(*args, **kwargs):
        raise espejo.AltaFallida("Un club agrega maestros, coaches y competidores.", 400)

    monkeypatch.setattr(auth_api, "alta_de_juez_en_dinamyt", rechaza)
    r = _alta(cliente, cabecera)

    assert r.status_code == 400
    assert "Un club agrega" in r.get_json()["error"]
    assert Usuario.query.filter_by(email="juez@nuevo.org").first() is None


def test_si_ya_es_de_la_organizacion_se_dice_que_entre_una_vez(con_puente, monkeypatch):
    cliente, cabecera, _, _ = con_puente

    def ya_es(*args, **kwargs):
        raise espejo.AltaFallida("El usuario ya es miembro de esta organización.", 400)

    monkeypatch.setattr(auth_api, "alta_de_juez_en_dinamyt", ya_es)
    r = _alta(cliente, cabecera)

    assert r.status_code == 400
    assert "entre una vez" in r.get_json()["error"]


# ══════════════════════════════════════════════════════════════════════════
#  3 · A una cuenta de DINAMYT no se le pone contraseña desde aquí
# ══════════════════════════════════════════════════════════════════════════

def test_no_se_le_pone_contrasena_a_una_cuenta_de_dinamyt(con_puente):
    cliente, cabecera, _, _ = con_puente
    uid = _alta(cliente, cabecera).get_json()["user"]["id"]

    r = cliente.put(f"/api/auth/users/{uid}", headers=cabecera, json={"password": "nueva123"})

    assert r.status_code == 409
    assert r.get_json()["motivo"] == "cuenta_de_dinamyt"
    assert not Usuario.query.get(uid).check_password("nueva123")


# ══════════════════════════════════════════════════════════════════════════
#  4 · Sin el puente, como siempre — sobre todo en el PC del evento
# ══════════════════════════════════════════════════════════════════════════

def test_sin_puente_el_alta_es_la_de_siempre(instalacion):
    _, cliente, cabecera, _ = instalacion
    assert cliente.get("/api/auth/alta", headers=cabecera).get_json() == {"en_dinamyt": False}

    r = _alta(cliente, cabecera, password="secret123")

    assert r.status_code == 201
    assert r.get_json()["cuenta"] == "local"
    assert Usuario.query.filter_by(email="juez@nuevo.org").one().check_password("secret123")


def test_en_el_pc_del_evento_se_crean_jueces_sin_internet(instalacion, monkeypatch):
    """F8 le pone `ECOSYSTEM_JWKS_URL` al PC del evento; el secreto, no."""
    aplicacion, cliente, cabecera, _ = instalacion
    aplicacion.config["ECOSYSTEM_JWKS_URL"] = JWKS
    monkeypatch.setenv("CAMPEONATOS_ONLINE_URL", "https://campeonatos.ejemplo.invalid")

    r = _alta(cliente, cabecera, password="secret123")

    assert r.status_code == 201
    assert r.get_json()["cuenta"] == "local"


def test_sin_puente_la_consola_si_pone_contrasenas(instalacion):
    _, cliente, cabecera, admin = instalacion
    r = cliente.put(f"/api/auth/users/{admin.id}", headers=cabecera, json={"password": "nueva123"})
    assert r.status_code == 200


# ══════════════════════════════════════════════════════════════════════════
#  5 · El cliente del alta
# ══════════════════════════════════════════════════════════════════════════

class _Respuesta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_el_cliente_pide_un_juez_de_campeonatos_con_el_secreto(con_puente, monkeypatch):
    enviado = {}

    def urlopen_falso(peticion, timeout=None):
        enviado["url"] = peticion.full_url
        enviado["cabeceras"] = dict(peticion.header_items())
        enviado["cuerpo"] = json.loads(peticion.data)
        return _Respuesta(json.dumps({"ecoSub": SUB_JUEZ, "cuenta": "nueva"}).encode())

    monkeypatch.setattr(espejo, "urlopen", urlopen_falso)
    datos = espejo.alta_de_juez_en_dinamyt("j@x.org", "JUEZ", ORG, SUB_ADMIN)

    assert datos["ecoSub"] == SUB_JUEZ
    assert enviado["url"] == "https://id.ejemplo.invalid/sync/alta"
    assert enviado["cabeceras"]["X-dinamyt-sync"] == "secreto-del-espejo"
    assert enviado["cuerpo"]["app"] == "campeonatos"
    assert enviado["cuerpo"]["role"] == "juez"
    assert enviado["cuerpo"]["ecoOrgId"] == ORG


def test_el_cliente_trae_el_motivo_de_dinamyt(con_puente, monkeypatch):
    def rechaza(peticion, timeout=None):
        raise HTTPError(peticion.full_url, 400, "Bad Request", {},
                        io.BytesIO(json.dumps({"message": "Falta el correo."}).encode()))

    monkeypatch.setattr(espejo, "urlopen", rechaza)
    with pytest.raises(espejo.AltaFallida) as exc:
        espejo.alta_de_juez_en_dinamyt("j@x.org", "JUEZ", ORG)
    assert exc.value.mensaje == "Falta el correo."
    assert exc.value.codigo == 400


def test_una_respuesta_sin_cuenta_es_un_error(con_puente, monkeypatch):
    monkeypatch.setattr(espejo, "urlopen",
                        lambda peticion, timeout=None: _Respuesta(b'{"cuenta": "nueva"}'))
    with pytest.raises(espejo.AltaFallida):
        espejo.alta_de_juez_en_dinamyt("j@x.org", "JUEZ", ORG)
