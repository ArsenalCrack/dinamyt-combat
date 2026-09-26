"""
El maestro inscribe a la gente de su club en DINAMYT (punto 2 de lo que
quedaba de `PLAN-CAMPEONATOS.md`, 25 de septiembre de 2026).

Hasta aquí el maestro elegía entre SUS fichas de Campeonatos, y a quien
competía por primera vez lo tecleaba: la ficha nacía sin enlace a su cuenta de
DINAMYT y la persona tenía que reclamarla después. Ahora:

  1. `/maestro/miembros` enseña la gente de su club en DINAMYT —sin el
     documento— y dice quién ya tiene ficha o ya está inscrito.
  2. Inscribir con `eco_sub` vuelve a preguntar a DINAMYT (el navegador no
     prueba nada), y la ficha nace ENLAZADA, con los datos de DINAMYT.
  3. La ficha de antes —sin enlace, con su documento— se reutiliza y se
     enlaza; la de otra cuenta con ese documento, no (409).
  4. Si DINAMYT no contesta, se dice (503); nunca se inventa.
"""

import io
import json
import sys
from pathlib import Path
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import create_app, espejo  # noqa: E402
from app.api import competidores as competidores_api  # noqa: E402
from app.config import DevelopmentConfig  # noqa: E402
from app.extensions import db  # noqa: E402

DevelopmentConfig.SQLALCHEMY_DATABASE_URI = "sqlite://"

SUB_MAESTRO = "22222222-2222-4222-8222-222222222222"
SUB_LUZ = "44444444-4444-4444-8444-444444444444"
SUB_OTRA = "55555555-5555-4555-8555-555555555555"

LUZ = {
    "sub": SUB_LUZ, "fullName": "Luz Marina Rojas", "birthDate": "2012-05-04",
    "gender": "FEMENINO", "documentId": "1088123456",
    "club": {"id": "c1", "name": "DOJANG SUR"}, "sinAcceso": False,
}


class Mundo:
    pass


@pytest.fixture()
def mundo(monkeypatch):
    app = create_app("development")
    with app.app_context():
        db.create_all()
        from flask_jwt_extended import create_access_token
        from app.models.campeonato import Campeonato
        from app.models.usuario import Usuario

        m = Mundo()
        m.admin = Usuario(email="a@fede.org", nombre="ADMIN", rol="admin", activo=True)
        m.admin.set_password("x")
        db.session.add(m.admin)
        db.session.commit()
        m.maestro = Usuario(email="maestro@sur.org", nombre="MAESTRO", rol="maestro",
                            activo=True, creado_por_id=m.admin.id, eco_sub=SUB_MAESTRO)
        m.maestro.set_password("x")
        m.maestro.clubes = ["DOJANG SUR"]
        m.local = Usuario(email="local@sur.org", nombre="LOCAL", rol="maestro",
                          activo=True, creado_por_id=m.admin.id)
        m.local.set_password("x")
        m.local.clubes = ["DOJANG SUR"]
        db.session.add_all([m.maestro, m.local])
        db.session.commit()
        m.camp = Campeonato(nombre="COPA", estado="preparacion", activo=True,
                            created_by=m.admin.id)
        m.camp2 = Campeonato(nombre="COPA 2", estado="preparacion", activo=True,
                             created_by=m.admin.id)
        db.session.add_all([m.camp, m.camp2])
        db.session.commit()

        m.preguntas = []
        m.dinamyt = [LUZ]

        def miembros_falso(maestro_sub, persona=None):
            m.preguntas.append((maestro_sub, persona))
            if m.dinamyt is None:
                return None
            return [x for x in m.dinamyt if persona is None or x["sub"] == persona]

        monkeypatch.setattr(competidores_api, "miembros_del_club", miembros_falso)
        m.cliente = app.test_client()
        m.h = {nombre: {"Authorization": f"Bearer {create_access_token(identity=str(getattr(m, nombre).id))}"}
               for nombre in ("admin", "maestro", "local")}
        yield m
        db.session.remove()
        db.drop_all()


def _miembros(m, quien="maestro", camp=None):
    camp = camp or m.camp
    r = m.cliente.get(f"/api/inscripciones/maestro/miembros?campeonato_id={camp.id}",
                      headers=m.h[quien])
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _inscribir(m, sub, camp=None, quien="maestro", **competidor):
    camp = camp or m.camp
    return m.cliente.post(
        f"/api/inscripciones/maestro/campeonato/{camp.id}",
        json={"eco_sub": sub, "competidor": {"club": "DOJANG SUR", "cinturon": "", **competidor},
              "modalidades": ["COMBATE"], "peso": 40},
        headers=m.h[quien],
    )


def _fichas():
    from app.models.competidor import Competidor

    db.session.expire_all()
    return Competidor.query.all()


# ══════════════════════════════════════════════════════════════════════════
#  1 · La lista
# ══════════════════════════════════════════════════════════════════════════

def test_la_lista_es_la_de_dinamyt_sin_el_documento(mundo):
    cuerpo = _miembros(mundo)

    assert cuerpo["disponible"] is True
    (luz,) = cuerpo["miembros"]
    assert luz["nombre_completo"] == "LUZ MARINA ROJAS"
    assert luz["fecha_nacimiento"] == "2012-05-04"
    assert luz["genero"] == "FEMENINO"
    assert luz["ficha_uid"] is None and luz["inscrito"] is False
    assert "documento" not in json.dumps(cuerpo) and "1088123456" not in json.dumps(cuerpo)
    assert mundo.preguntas == [(SUB_MAESTRO, None)]


def test_quien_entro_con_contrasena_no_tiene_club_en_dinamyt(mundo):
    assert _miembros(mundo, "local") == {"disponible": False, "motivo": "sin_cuenta", "miembros": []}


def test_sin_dinamyt_se_dice_y_no_se_inventa(mundo):
    mundo.dinamyt = None
    assert _miembros(mundo)["motivo"] == "sin_dinamyt"


# ══════════════════════════════════════════════════════════════════════════
#  2 · Inscribir: se vuelve a preguntar, y la ficha nace enlazada
# ══════════════════════════════════════════════════════════════════════════

def test_la_ficha_nace_enlazada_y_con_los_datos_de_dinamyt(mundo):
    r = _inscribir(mundo, SUB_LUZ, nombre_completo="OTRO NOMBRE", fecha_nacimiento="2000-01-01")

    assert r.status_code == 201, r.get_json()
    (ficha,) = _fichas()
    assert ficha.eco_sub == SUB_LUZ
    # Lo que dice DINAMYT manda sobre lo tecleado.
    assert ficha.nombre_completo == "LUZ MARINA ROJAS"
    assert ficha.fecha_nacimiento.isoformat() == "2012-05-04"
    assert ficha.documento == "1088123456"
    assert ficha.club == "DOJANG SUR"
    assert (SUB_MAESTRO, SUB_LUZ) in mundo.preguntas
    assert r.get_json()["inscripcion"]["estado"] == "pendiente"

    luz = _miembros(mundo)["miembros"][0]
    assert luz["ficha_uid"] == ficha.uid and luz["inscrito"] is True


def test_en_el_segundo_campeonato_se_reutiliza_la_misma_ficha(mundo):
    assert _inscribir(mundo, SUB_LUZ).status_code == 201
    r = _inscribir(mundo, SUB_LUZ, camp=mundo.camp2)
    assert r.status_code == 201, r.get_json()
    assert r.get_json()["reutilizada"] is True
    assert len(_fichas()) == 1


def test_alguien_que_no_es_de_su_club_no_se_inscribe(mundo):
    r = _inscribir(mundo, SUB_OTRA)
    assert r.status_code == 404
    assert _fichas() == []


def test_si_dinamyt_no_contesta_no_se_inscribe_a_ciegas(mundo):
    mundo.dinamyt = None
    assert _inscribir(mundo, SUB_LUZ).status_code == 503
    assert _fichas() == []


def test_sin_cuenta_de_dinamyt_no_se_puede_mandar_un_eco_sub(mundo):
    assert _inscribir(mundo, SUB_LUZ, quien="local").status_code == 409
    assert _fichas() == []


# ══════════════════════════════════════════════════════════════════════════
#  3 · La ficha de antes
# ══════════════════════════════════════════════════════════════════════════

def _ficha_vieja(eco_sub=None):
    from app.models.competidor import Competidor

    from app.models.usuario import Usuario

    admin = Usuario.query.filter_by(email="a@fede.org").one()
    vieja = Competidor(nombre_completo="LUZ M ROJAS", documento="1088123456",
                       genero="FEMENINO", club="DOJANG SUR", activo=True,
                       created_by=admin.id, eco_sub=eco_sub)
    db.session.add(vieja)
    db.session.commit()
    return vieja.id


def test_la_ficha_de_antes_con_su_documento_se_reutiliza_y_se_enlaza(mundo):
    vieja = _ficha_vieja()

    r = _inscribir(mundo, SUB_LUZ)

    assert r.status_code == 201, r.get_json()
    (ficha,) = _fichas()
    assert ficha.id == vieja
    assert ficha.eco_sub == SUB_LUZ


def test_un_documento_de_otra_cuenta_no_se_pisa(mundo):
    _ficha_vieja(eco_sub=SUB_OTRA)

    r = _inscribir(mundo, SUB_LUZ)

    assert r.status_code == 409
    assert [f.eco_sub for f in _fichas()] == [SUB_OTRA]


# ══════════════════════════════════════════════════════════════════════════
#  4 · El cliente de DINAMYT
# ══════════════════════════════════════════════════════════════════════════

class _Respuesta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_el_cliente_pregunta_en_nombre_del_maestro_y_por_una_persona(monkeypatch):
    app = create_app("development")
    app.config["ECOSYSTEM_JWKS_URL"] = "https://id.ejemplo.invalid/auth/jwks"
    monkeypatch.setenv("ECOSYSTEM_SYNC_SECRET", "secreto")
    enviado = {}

    def urlopen_falso(peticion, timeout=None):
        enviado["url"] = peticion.full_url
        enviado["cabeceras"] = dict(peticion.header_items())
        return _Respuesta(json.dumps([LUZ, {"sin": "sub"}]).encode())

    monkeypatch.setattr(espejo, "urlopen", urlopen_falso)
    with app.app_context():
        lista = espejo.miembros_del_club(SUB_MAESTRO, persona=SUB_LUZ)

    assert [m["sub"] for m in lista] == [SUB_LUZ]
    assert enviado["url"] == (
        f"https://id.ejemplo.invalid/sync/miembros?maestro={SUB_MAESTRO}&persona={SUB_LUZ}"
    )
    assert enviado["cabeceras"]["X-dinamyt-sync"] == "secreto"


def test_el_cliente_sin_puente_o_con_error_contesta_none(monkeypatch):
    app = create_app("development")
    monkeypatch.delenv("ECOSYSTEM_SYNC_SECRET", raising=False)
    with app.app_context():
        assert espejo.miembros_del_club(SUB_MAESTRO) is None

    app.config["ECOSYSTEM_JWKS_URL"] = "https://id.ejemplo.invalid/auth/jwks"
    monkeypatch.setenv("ECOSYSTEM_SYNC_SECRET", "secreto")

    def rechaza(peticion, timeout=None):
        raise HTTPError(peticion.full_url, 401, "No", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr(espejo, "urlopen", rechaza)
    with app.app_context():
        assert espejo.miembros_del_club(SUB_MAESTRO) is None
