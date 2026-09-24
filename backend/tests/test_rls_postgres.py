"""
La red de RLS contra un PostgreSQL DE VERDAD.

El resto de la batería corre en SQLite, donde RLS no existe (`app/rls.py` es un
no-op ahí). Así que toda regla de aislamiento que dependa de las políticas —y
no del filtro de la API— estaba sin probar: producción usa PostgreSQL con
`FORCE ROW LEVEL SECURITY` y un rol normal (`OPERAR.md`), y lo que allí falla,
aquí pasa en verde.

Se salta solo si no hay base: hace falta `CAMPEONATOS_PG_URL` apuntando a una
base VACÍA cuyo dueño sea un rol SIN superusuario ni BYPASSRLS —si no, las
políticas no filtran nada y la prueba no mide lo que dice—. Por ejemplo, un
clúster de usar y tirar:

    initdb -D pgdata -U postgres -A trust
    pg_ctl -D pgdata -o "-p 55432" start
    psql -p 55432 -U postgres -c "CREATE ROLE camp LOGIN" -c "CREATE DATABASE camp_test OWNER camp"
    set CAMPEONATOS_PG_URL=postgresql://camp@127.0.0.1:55432/camp_test
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

URL = os.getenv("CAMPEONATOS_PG_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not URL, reason="Sin CAMPEONATOS_PG_URL: RLS solo existe en PostgreSQL."
)


def _token(user):
    from flask_jwt_extended import create_access_token

    return create_access_token(
        identity=str(user.id),
        additional_claims={"rol": user.rol, "nombre": user.nombre, "email": user.email},
    )


@pytest.fixture()
def pg():
    """App contra PostgreSQL, con las políticas puestas y comprobadas."""
    from app import create_app
    from app.config import DevelopmentConfig
    from app.extensions import db

    from app.config import ProductionConfig

    # Los demás módulos fijan SQLite en la clase al importarse; aquí se cambia
    # solo mientras dura la prueba. Y con las opciones de motor de PRODUCCIÓN
    # (`NullPool`): las de desarrollo llevan un `timeout` que solo entiende
    # SQLite.
    antes = (
        DevelopmentConfig.SQLALCHEMY_DATABASE_URI,
        DevelopmentConfig.SQLALCHEMY_ENGINE_OPTIONS,
    )
    DevelopmentConfig.SQLALCHEMY_DATABASE_URI = URL
    DevelopmentConfig.SQLALCHEMY_ENGINE_OPTIONS = ProductionConfig.SQLALCHEMY_ENGINE_OPTIONS
    try:
        app = create_app("development")
    finally:
        (
            DevelopmentConfig.SQLALCHEMY_DATABASE_URI,
            DevelopmentConfig.SQLALCHEMY_ENGINE_OPTIONS,
        ) = antes

    with app.app_context():
        db.drop_all()
        db.create_all()
        from app.schema_compat import ensure_optional_columns
        from app.rls import ensure_rls, estado_rls

        ensure_optional_columns()
        db.session.commit()
        _, fallos = ensure_rls()
        assert not fallos, fallos
        ok, motivo = estado_rls()
        assert ok, f"RLS no protege en esta base: {motivo}"
        yield app, db
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def club(pg):
    """Un admin, su maestro con dojang y un campeonato en preparación."""
    app, db = pg
    from app.models.campeonato import Campeonato
    from app.models.usuario import Usuario

    admin = Usuario(email="admin@t.local", nombre="ADMIN", rol="admin", activo=True)
    admin.set_password("secret123")
    db.session.add(admin)
    db.session.commit()
    maestro = Usuario(email="maestro@t.local", nombre="MAESTRO", rol="maestro",
                      activo=True, creado_por_id=admin.id)
    maestro.clubes = ["DOJANG SUR"]
    maestro.set_password("secret123")
    db.session.add(maestro)
    camp = Campeonato(nombre="COPA", estado="preparacion", activo=True, created_by=admin.id)
    db.session.add(camp)
    db.session.commit()
    return app.test_client(), {"admin": _token(admin), "maestro": _token(maestro)}, camp.id


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _sembrar():
    """Devuelve el acceso total antes de escribir a mano en la base.

    El cliente de pruebas comparte el contexto de la app, así que después de
    una petición `g` se queda con la red del último usuario — y lo que la
    prueba siembre a mano caería dentro. En producción no pasa: cada petición
    trae su propio contexto.
    """
    from app.rls import fijar_contexto

    fijar_contexto(None, True)


ALUMNA = {
    "nombre_completo": "ANA GOMEZ",
    "fecha_nacimiento": "2012-05-04",
    "genero": "F",
    "documento": "1088123456",
    "grupo_cinturon": "color",
    "club": "DOJANG SUR",
}


def test_el_maestro_inscribe_y_el_admin_ve_la_solicitud(club):
    """La moderación entera, con la red puesta.

    El maestro envía la solicitud, él la ve en «mis solicitudes», y el admin la
    ve en su campeonato para aceptarla. Cada paso pasa por una política de RLS
    distinta, y en SQLite ninguno.
    """
    cliente, tokens, camp_id = club
    r = cliente.post(
        f"/api/inscripciones/maestro/campeonato/{camp_id}",
        json={"competidor": ALUMNA, "peso": 40},
        headers=_h(tokens["maestro"]),
    )
    assert r.status_code == 201, r.get_json()

    mias = cliente.get("/api/inscripciones/maestro/mias", headers=_h(tokens["maestro"]))
    assert mias.status_code == 200
    assert len(mias.get_json()) == 1

    del_admin = cliente.get(
        f"/api/inscripciones/campeonato/{camp_id}", headers=_h(tokens["admin"])
    )
    assert del_admin.status_code == 200
    assert [i["estado"] for i in del_admin.get_json()] == ["pendiente"]


def _inscribir(cliente, tokens, camp_id, **extra):
    return cliente.post(
        f"/api/inscripciones/maestro/campeonato/{camp_id}",
        json={"competidor": ALUMNA, "peso": 40, **extra},
        headers=_h(tokens["maestro"]),
    )


def test_el_admin_rechaza_y_el_maestro_corrige(club):
    """Rechazar, ver el motivo y reenviar: tres escrituras con la red puesta."""
    cliente, tokens, camp_id = club
    ins = _inscribir(cliente, tokens, camp_id).get_json()["inscripcion"]

    r = cliente.patch(
        f"/api/inscripciones/{ins['id']}/estado",
        json={"estado": "rechazada", "motivo": "Falta el peso real"},
        headers=_h(tokens["admin"]),
    )
    assert r.status_code == 200, r.get_json()

    mias = cliente.get("/api/inscripciones/maestro/mias", headers=_h(tokens["maestro"]))
    assert mias.get_json()[0]["motivo_rechazo"] == "Falta el peso real"

    r = cliente.put(
        f"/api/inscripciones/maestro/{ins['id']}",
        json={"competidor": ALUMNA, "peso": 41},
        headers=_h(tokens["maestro"]),
    )
    assert r.status_code == 200, r.get_json()

    r = cliente.patch(
        f"/api/inscripciones/{ins['id']}/estado",
        json={"estado": "aceptada"},
        headers=_h(tokens["admin"]),
    )
    assert r.status_code == 200, r.get_json()


def test_otro_admin_no_ve_ni_modera_lo_ajeno(pg, club):
    """La red sigue separando workspaces: el arreglo no abrió nada."""
    app, db = pg
    cliente, tokens, camp_id = club
    ins = _inscribir(cliente, tokens, camp_id).get_json()["inscripcion"]

    from app.models.usuario import Usuario

    _sembrar()
    otro = Usuario(email="otro@t.local", nombre="OTRO", rol="admin", activo=True)
    otro.set_password("secret123")
    db.session.add(otro)
    db.session.commit()
    t_otro = _token(otro)

    assert cliente.get(
        f"/api/inscripciones/campeonato/{camp_id}", headers=_h(t_otro)
    ).status_code == 404
    assert cliente.patch(
        f"/api/inscripciones/{ins['id']}/estado",
        json={"estado": "aceptada"},
        headers=_h(t_otro),
    ).status_code == 404


def test_el_maestro_no_inscribe_en_el_campeonato_de_otro_admin(pg, club):
    app, db = pg
    cliente, tokens, _ = club
    from app.models.campeonato import Campeonato
    from app.models.usuario import Usuario

    otro = Usuario(email="otro@t.local", nombre="OTRO", rol="admin", activo=True)
    otro.set_password("secret123")
    db.session.add(otro)
    db.session.commit()
    ajeno = Campeonato(nombre="AJENO", estado="preparacion", activo=True, created_by=otro.id)
    db.session.add(ajeno)
    db.session.commit()

    assert _inscribir(cliente, tokens, ajeno.id).status_code == 404


def test_el_admin_crea_un_campeonato_con_la_red_puesta(club):
    cliente, tokens, _ = club
    r = cliente.post(
        "/api/campeonatos",
        json={"nombre": "Copa Nueva", "num_tatamis": 2},
        headers=_h(tokens["admin"]),
    )
    assert r.status_code == 201, r.get_json()
    lista = cliente.get("/api/campeonatos", headers=_h(tokens["admin"])).get_json()
    assert "COPA NUEVA" in [c["nombre"] for c in lista]


def test_el_panel_del_competidor_ve_su_ficha_de_otro_workspace(pg, club):
    """`/api/mi/*` levanta la red y acota por `eco_sub`: con PostgreSQL de verdad."""
    app, db = pg
    cliente, tokens, camp_id = club
    ins = _inscribir(cliente, tokens, camp_id).get_json()["inscripcion"]
    cliente.patch(
        f"/api/inscripciones/{ins['id']}/estado",
        json={"estado": "aceptada"},
        headers=_h(tokens["admin"]),
    )

    from app.models.competidor import Competidor
    from app.models.usuario import Usuario

    _sembrar()
    sub = "11111111-2222-3333-4444-555555555555"
    ficha = Competidor.query.filter_by(documento=ALUMNA["documento"]).first()
    ficha.eco_sub = sub
    alumna = Usuario(email="ana@t.local", nombre="ANA GOMEZ", rol="competidor",
                     activo=True, eco_sub=sub)
    alumna.set_password("secret123")
    db.session.add(alumna)
    db.session.commit()

    r = cliente.get("/api/mi/panel", headers=_h(_token(alumna)))
    assert r.status_code == 200, r.get_json()
    cuerpo = r.get_json()
    assert len(cuerpo["fichas"]) == 1
    assert [i["estado"] for i in cuerpo["inscripciones"]] == ["aceptada"]


def test_la_organizacion_de_los_campeonatos_se_rellena_en_postgres(pg):
    """F4: el relleno es SQL a mano; tiene que valer en el motor de producción."""
    app, db = pg
    from app.models.campeonato import Campeonato
    from app.models.usuario import Usuario
    from app.organizacion import rellenar_org_de_campeonatos

    admin = Usuario(email="admin@t.local", nombre="ADMIN", rol="admin", activo=True,
                    org_id="0f000000-0000-4000-8000-00000000fede")
    admin.set_password("secret123")
    db.session.add(admin)
    db.session.commit()
    db.session.add(Campeonato(nombre="VIEJO", created_by=admin.id))
    db.session.commit()

    assert rellenar_org_de_campeonatos() == 1
    db.session.commit()
    assert Campeonato.query.one().org_id == admin.org_id
