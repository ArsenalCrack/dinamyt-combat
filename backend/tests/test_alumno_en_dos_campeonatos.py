"""
El mismo alumno, en DOS campeonatos. Que es lo normal, y hoy no se puede.

── Lo que hace hoy `maestro_inscribir` ──────────────────────────────────────

    comp = Competidor(nombre_completo="", activo=True, created_by=...)

Una fila NUEVA en cada inscripción, siempre. No busca si ese alumno ya existe.
De ahí salen las dos mitades del problema, y son excluyentes:

  · **Con documento** — `documento` es único en TODO el sistema, así que la
    segunda inscripción se rechaza con «Ya existe un competidor con documento
    X». El maestro no puede inscribir a su propio alumno en el segundo
    campeonato del año.

  · **Sin documento** — pasa, pero deja DOS filas distintas para la misma
    persona. Y sin una ficha estable no hay historial: «mis resultados» no se
    puede armar, porque no hay nadie de quien sean.

Estas pruebas fijan el comportamiento actual para que el arreglo tenga contra
qué medirse. Cuando la inscripción reutilice la ficha, las dos primeras cambian
de signo y hay que reescribirlas — a propósito.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import create_app  # noqa: E402
from app.config import DevelopmentConfig  # noqa: E402
from app.extensions import db  # noqa: E402

DevelopmentConfig.SQLALCHEMY_DATABASE_URI = "sqlite://"


def _token(user):
    from flask_jwt_extended import create_access_token

    return create_access_token(
        identity=str(user.id),
        additional_claims={"rol": user.rol, "nombre": user.nombre, "email": user.email},
    )


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def entorno():
    """Un admin, su maestro, y DOS campeonatos en preparación."""
    app = create_app("development")
    with app.app_context():
        db.create_all()
        from app.models.campeonato import Campeonato
        from app.models.usuario import Usuario

        admin = Usuario(email="admin@test.local", nombre="ADMIN", rol="admin",
                        es_superadmin=True, activo=True)
        admin.set_password("secret123")
        db.session.add(admin)
        db.session.commit()

        maestro = Usuario(email="maestro@test.local", nombre="MAESTRO",
                          rol="maestro", activo=True, creado_por_id=admin.id)
        maestro.set_password("secret123")
        maestro.clubes = ["Dojang Sur"]
        db.session.add(maestro)
        db.session.commit()

        primera = Campeonato(nombre="COPA DE MARZO", estado="preparacion",
                             activo=True, created_by=admin.id)
        segunda = Campeonato(nombre="COPA DE AGOSTO", estado="preparacion",
                             activo=True, created_by=admin.id)
        db.session.add_all([primera, segunda])
        db.session.commit()

        yield app, _token(maestro), primera.id, segunda.id
        db.session.remove()
        db.drop_all()


def _inscribir(cliente, token, camp_id, *, documento=None, peso=None):
    competidor = {
        "nombre_completo": "ANA GOMEZ",
        "fecha_nacimiento": "2008-05-04",
        "genero": "FEMENINO",
        "cinturon": "Negro",
        "club": "Dojang Sur",
    }
    if documento:
        competidor["documento"] = documento
    cuerpo = {"competidor": competidor, "modalidades": ["COMBATE"]}
    if peso is not None:
        cuerpo["peso"] = peso
    return cliente.post(
        f"/api/inscripciones/maestro/campeonato/{camp_id}",
        headers=_auth(token),
        json=cuerpo,
    )


class TestElMismoAlumnoDosVeces:
    def test_con_documento_la_segunda_inscripcion_SE_RECHAZA(self, entorno):
        """El caso real: la misma alumna, el segundo campeonato del año."""
        app, token, primera, segunda = entorno
        cliente = app.test_client()

        assert _inscribir(cliente, token, primera, documento="1088123456").status_code == 201

        repetida = _inscribir(cliente, token, segunda, documento="1088123456")
        assert repetida.status_code == 400
        assert "Ya existe un competidor con documento" in repetida.get_json()["error"]

    def test_sin_documento_pasa_pero_deja_DOS_fichas(self, entorno):
        """Y sin ficha estable no hay historial de quien compite dos veces."""
        app, token, primera, segunda = entorno
        cliente = app.test_client()

        assert _inscribir(cliente, token, primera).status_code == 201
        assert _inscribir(cliente, token, segunda).status_code == 201

        with app.app_context():
            from app.models.competidor import Competidor

            fichas = Competidor.query.filter_by(nombre_completo="ANA GOMEZ").all()
            assert len(fichas) == 2
            assert fichas[0].id != fichas[1].id

    def test_el_maestro_reescribe_todos_los_datos_cada_vez(self, entorno):
        """
        No hay ninguna ruta que le diga al maestro quiénes son sus alumnos.

        Lo que se inscribe es lo que venga en el cuerpo, siempre: no hay de
        dónde precargar. Por eso el peso —que sí cambia entre campeonatos— y el
        nombre, la fecha y el cinturón —que no— cuestan lo mismo de teclear.
        """
        app, token, primera, _ = entorno
        cliente = app.test_client()

        assert _inscribir(cliente, token, primera, peso=52.5).status_code == 201

        # No existe «mis alumnos»: lo más cercano es el listado de competidores,
        # y es solo del admin.
        assert cliente.get(
            "/api/inscripciones/maestro/alumnos", headers=_auth(token)
        ).status_code == 404
