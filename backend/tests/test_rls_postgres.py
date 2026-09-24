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
