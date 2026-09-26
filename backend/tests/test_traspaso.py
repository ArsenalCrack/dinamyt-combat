"""
La organización manda: el traspaso del workspace (F4, punto 3 de
`PLAN-CAMPEONATOS.md`, hecho el 25 de septiembre de 2026).

El punto 3 decía «`es_dueno_campeonato` compara `org_id`». No se hizo así: RLS
filtra por `created_by`, y un segundo admin vería el campeonato sin sus
llaves ni sus fichas. Lo que resuelve el caso real —cambió el admin de la
organización— es MOVER el workspace. Lo que se defiende:

  1. Solo el superadministrador, y solo entre admins de la misma organización.
  2. En seco no escribe nada y dice qué movería.
  3. Aplicado, TODO pasa al nuevo: campeonatos, fichas, llaves, resultados
     publicados, inscripciones hechas a mano y su gente.
  4. Con fichas del mismo documento en los dos workspaces, se niega.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import create_app  # noqa: E402
from app.config import DevelopmentConfig  # noqa: E402
from app.extensions import db  # noqa: E402

DevelopmentConfig.SQLALCHEMY_DATABASE_URI = "sqlite://"

ORG = "0f000000-0000-4000-8000-00000000fede"
OTRA = "0f000000-0000-4000-8000-0000000000aa"


class Mundo:
    pass


def _token(user):
    from flask_jwt_extended import create_access_token

    return {"Authorization": f"Bearer {create_access_token(identity=str(user.id))}"}


@pytest.fixture()
def mundo():
    app = create_app("development")
    with app.app_context():
        db.create_all()
        m = Mundo()
        m.app = app
        m.cliente = app.test_client()
        _sembrar(m)
        yield m
        db.session.remove()
        db.drop_all()


def _sembrar(m):
    from app.models.campeonato import Campeonato
    from app.models.competidor import Competidor, Inscripcion
    from app.models.llave import Llave
    from app.models.resultado_publicado import ResultadoPublicado
    from app.models.usuario import Usuario

    def usuario(email, rol="admin", **extra):
        u = Usuario(email=email, nombre=email.split("@")[0].upper(), rol=rol, activo=True, **extra)
        u.set_password("x")
        db.session.add(u)
        db.session.commit()
        return u

    m.super = usuario("super@t.org", es_superadmin=True)
    m.viejo = usuario("viejo@fede.org", org_id=ORG)
    m.nuevo = usuario("nuevo@fede.org", org_id=ORG)
    m.ajeno = usuario("ajeno@otra.org", org_id=OTRA)
    m.juez = usuario("juez@fede.org", rol="juez", creado_por_id=m.viejo.id)

    m.camp = Campeonato(nombre="COPA VIEJA", estado="preparacion", activo=True,
                        created_by=m.viejo.id)
    db.session.add(m.camp)
    db.session.flush()
    m.ficha = Competidor(nombre_completo="ANA", documento="111", genero="FEMENINO",
                         fecha_nacimiento=date(2012, 5, 4), activo=True, created_by=m.viejo.id)
    db.session.add(m.ficha)
    db.session.flush()
    db.session.add_all([
        Inscripcion(campeonato_id=m.camp.id, competidor_id=m.ficha.id, estado="aceptada",
                    created_by=m.viejo.id),
        Llave(campeonato_id=m.camp.id, tipo="combate", nombre="L", created_by=m.viejo.id,
              estructura={"competidores": []}),
        ResultadoPublicado(export_uuid="e" * 32, nombre="COPA VIEJA", payload={},
                           created_by=m.viejo.id),
    ])
    db.session.commit()


def _traspasar(m, quien=None, **cuerpo):
    quien = quien or m.super
    base = {"de": m.viejo.id, "a": m.nuevo.id}
    base.update(cuerpo)
    return m.cliente.post("/api/auth/organizaciones/traspasar", json=base, headers=_token(quien))


def _duenos():
    from app.models.campeonato import Campeonato
    from app.models.competidor import Competidor, Inscripcion
    from app.models.llave import Llave
    from app.models.resultado_publicado import ResultadoPublicado
    from app.models.usuario import Usuario

    db.session.expire_all()
    return {
        "campeonato": Campeonato.query.one().created_by,
        "ficha": Competidor.query.one().created_by,
        "inscripcion": Inscripcion.query.one().created_by,
        "llave": Llave.query.one().created_by,
        "publicado": ResultadoPublicado.query.one().created_by,
        "juez": Usuario.query.filter_by(email="juez@fede.org").one().creado_por_id,
    }


# ── 1 · Quién, y entre quiénes ─────────────────────────────────────────────

def test_solo_el_superadministrador(mundo):
    assert _traspasar(mundo, quien=mundo.nuevo).status_code == 403
    assert set(_duenos().values()) == {mundo.viejo.id}


@pytest.mark.parametrize("cuerpo, codigo", [
    ({"a": "__ajeno__"}, 400),   # de otra organización
    ({"a": "__viejo__"}, 400),   # el mismo
    ({"a": "__juez__"}, 404),    # no es admin
    ({"de": "x"}, 400),          # no es un id
])
def test_solo_entre_admins_de_la_misma_organizacion(mundo, cuerpo, codigo):
    ids = {"__ajeno__": mundo.ajeno.id, "__viejo__": mundo.viejo.id, "__juez__": mundo.juez.id}
    cuerpo = {k: ids.get(v, v) for k, v in cuerpo.items()}
    r = _traspasar(mundo, **cuerpo)
    assert r.status_code == codigo, r.get_json()
    assert set(_duenos().values()) == {mundo.viejo.id}


# ── 2 · En seco ─────────────────────────────────────────────────────────────

def test_en_seco_dice_que_movera_y_no_toca_nada(mundo):
    r = _traspasar(mundo)

    assert r.status_code == 200, r.get_json()
    cuerpo = r.get_json()
    assert cuerpo["aplicado"] is False
    assert cuerpo["filas"] == {
        "campeonatos": 1, "competidores": 1, "llaves": 1,
        "resultados_publicados": 1, "inscripciones": 1, "usuarios": 1,
    }
    assert cuerpo["choques"] == []
    assert set(_duenos().values()) == {mundo.viejo.id}


# ── 3 · Aplicado ────────────────────────────────────────────────────────────

def test_aplicado_todo_pasa_al_nuevo_y_el_nuevo_lo_ve(mundo):
    r = _traspasar(mundo, aplicar=True)

    assert r.status_code == 200, r.get_json()
    assert r.get_json()["aplicado"] is True
    assert set(_duenos().values()) == {mundo.nuevo.id}

    from app.models.campeonato import Campeonato

    assert Campeonato.query.one().org_id == ORG
    lista = mundo.cliente.get("/api/campeonatos", headers=_token(mundo.nuevo)).get_json()
    assert [c["nombre"] for c in lista] == ["COPA VIEJA"]
    assert mundo.cliente.get("/api/campeonatos", headers=_token(mundo.viejo)).get_json() == []


# ── 4 · Los choques ─────────────────────────────────────────────────────────

def test_el_mismo_documento_en_los_dos_se_niega(mundo):
    from app.models.competidor import Competidor

    db.session.add(Competidor(nombre_completo="ANA B", documento="111", activo=True,
                              created_by=mundo.nuevo.id))
    db.session.commit()

    seco = _traspasar(mundo).get_json()
    assert [c["documento"] for c in seco["choques"]] == ["111"]

    r = _traspasar(mundo, aplicar=True)
    assert r.status_code == 409
    from app.models.campeonato import Campeonato

    db.session.expire_all()
    assert Campeonato.query.one().created_by == mundo.viejo.id
    assert Competidor.query.filter_by(created_by=mundo.viejo.id).count() == 1
