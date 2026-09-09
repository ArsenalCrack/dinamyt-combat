"""
El mismo alumno, en DOS campeonatos. Que es lo normal, y ahora sí se puede.

── Lo que hacía `maestro_inscribir` antes de F5-bis ─────────────────────────

    comp = Competidor(nombre_completo="", activo=True, created_by=...)

Una fila NUEVA en cada inscripción, siempre. De ahí salían las dos mitades del
problema, y eran excluyentes:

  · **Con documento** — `documento` es único en TODO el sistema, así que la
    segunda inscripción se rechazaba con «Ya existe un competidor con documento
    X». El maestro no podía inscribir a su propio alumno en el segundo
    campeonato del año.

  · **Sin documento** — pasaba, pero dejaba DOS filas para la misma persona. Y
    sin una ficha estable no hay historial: «mis resultados» no se puede armar,
    porque no hay nadie de quien sean.

Estas pruebas nacieron fijando ese comportamiento roto, para que el arreglo
tuviera contra qué medirse. Ahora dicen lo contrario, que era el plan: **la
ficha se reutiliza**. Se conserva el reparto original —una prueba por mitad—
para que se lea el antes y el después en el mismo sitio.

Lo que se comprueba aquí, en orden:
  1. El documento repetido reutiliza la ficha en vez de rechazarla.
  2. Sin documento, el maestro elige al alumno de su lista (`competidor_uid`).
  3. Esa lista existe: `GET /maestro/alumnos` (antes 404).
  4. El peso es de la inscripción, no de la ficha.
  5. Dos veces en el MISMO campeonato sigue sin poder ser (409, no 500).
  6. El aislamiento por workspace no se rompe al reutilizar.
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


def _inscribir(cliente, token, camp_id, *, documento=None, peso=None, uid=None):
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
    if uid is not None:
        cuerpo["competidor_uid"] = uid
    return cliente.post(
        f"/api/inscripciones/maestro/campeonato/{camp_id}",
        headers=_auth(token),
        json=cuerpo,
    )


def _fichas(app, nombre="ANA GOMEZ"):
    with app.app_context():
        from app.models.competidor import Competidor

        return Competidor.query.filter_by(nombre_completo=nombre).all()


class TestElMismoAlumnoDosVeces:
    def test_con_documento_la_segunda_inscripcion_REUTILIZA_LA_FICHA(self, entorno):
        """El caso real: la misma alumna, el segundo campeonato del año.

        Antes: 400 «Ya existe un competidor con documento…». Un documento
        repetido nunca fue un error del maestro — era el sistema sin entender
        que las personas vuelven.
        """
        app, token, primera, segunda = entorno
        cliente = app.test_client()

        assert _inscribir(cliente, token, primera, documento="1088123456").status_code == 201

        repetida = _inscribir(cliente, token, segunda, documento="1088123456")
        assert repetida.status_code == 201
        assert repetida.get_json()["reutilizada"] is True

        fichas = _fichas(app)
        assert len(fichas) == 1
        assert fichas[0].documento == "1088123456"

        with app.app_context():
            from app.models.competidor import Inscripcion

            inscripciones = Inscripcion.query.filter_by(competidor_id=fichas[0].id).all()
            assert {i.campeonato_id for i in inscripciones} == {primera, segunda}

    def test_sin_documento_el_maestro_ELIGE_al_alumno_de_su_lista(self, entorno):
        """Y con una sola ficha ya hay de dónde colgar el historial.

        Sin documento no hay clave natural que emparejar, así que la segunda
        inscripción manda el `competidor_uid` que le dio `/maestro/alumnos`.
        """
        app, token, primera, segunda = entorno
        cliente = app.test_client()

        assert _inscribir(cliente, token, primera).status_code == 201

        alumnos = cliente.get(
            "/api/inscripciones/maestro/alumnos", headers=_auth(token)
        ).get_json()
        assert len(alumnos) == 1
        uid = alumnos[0]["uid"]
        assert uid

        segunda_vez = _inscribir(cliente, token, segunda, uid=uid)
        assert segunda_vez.status_code == 201
        assert segunda_vez.get_json()["reutilizada"] is True

        fichas = _fichas(app)
        assert len(fichas) == 1

    def test_el_maestro_ya_tiene_la_lista_de_sus_alumnos(self, entorno):
        """La ruta que antes devolvía 404, que era el motivo de teclearlo todo.

        El nombre, la fecha, el género y el cinturón no cambian nunca: ahora
        vienen de la ficha. Y cada alumno dice si ya está en ESE campeonato,
        para no ofrecerlo dos veces.
        """
        app, token, primera, segunda = entorno
        cliente = app.test_client()

        assert _inscribir(cliente, token, primera, peso=52.5).status_code == 201

        respuesta = cliente.get(
            f"/api/inscripciones/maestro/alumnos?campeonato_id={primera}",
            headers=_auth(token),
        )
        assert respuesta.status_code == 200
        alumno = respuesta.get_json()[0]
        assert alumno["nombre_completo"] == "ANA GOMEZ"
        assert alumno["fecha_nacimiento"] == "2008-05-04"
        assert alumno["cinturon"] == "Negro"
        assert alumno["inscrito"] is True
        assert alumno["estado_inscripcion"] == "pendiente"

        # En el otro campeonato la misma alumna todavía no está.
        otro = cliente.get(
            f"/api/inscripciones/maestro/alumnos?campeonato_id={segunda}",
            headers=_auth(token),
        ).get_json()[0]
        assert otro["inscrito"] is False

    def test_el_peso_es_de_la_inscripcion_no_de_la_ficha(self, entorno):
        """El peso del año pasado no contamina el de este.

        Es lo único que el maestro escribe en cada campeonato, y por eso es lo
        único que NO puede vivir en la ficha compartida.
        """
        app, token, primera, segunda = entorno
        cliente = app.test_client()

        assert _inscribir(cliente, token, primera, documento="1088123456",
                          peso=52.5).status_code == 201
        assert _inscribir(cliente, token, segunda, documento="1088123456",
                          peso=55.0).status_code == 201

        with app.app_context():
            from app.models.competidor import Competidor, Inscripcion

            ficha = Competidor.query.filter_by(documento="1088123456").one()
            pesos = {
                i.campeonato_id: i.peso
                for i in Inscripcion.query.filter_by(competidor_id=ficha.id).all()
            }
            assert pesos == {primera: 52.5, segunda: 55.0}
            # La ficha se quedó con el primero: la segunda inscripción no la pisó.
            assert ficha.peso == 52.5

    def test_dos_veces_en_el_MISMO_campeonato_sigue_sin_poder_ser(self, entorno):
        """Y se dice con una frase, no con un 500.

        La inscripción es única por (campeonato, competidor). Antes esa
        restricción no llegaba a tocarse nunca, porque cada inscripción
        estrenaba ficha.
        """
        app, token, primera, _ = entorno
        cliente = app.test_client()

        assert _inscribir(cliente, token, primera, documento="1088123456").status_code == 201
        repetida = _inscribir(cliente, token, primera, documento="1088123456")
        assert repetida.status_code == 409
        assert "ya está en este campeonato" in repetida.get_json()["error"]


class TestElAislamientoSigueEnPie:
    """Reutilizar la ficha no puede abrir la de otro administrador."""

    def test_el_documento_de_otro_workspace_sigue_siendo_un_error(self, entorno):
        app, token, primera, _ = entorno
        cliente = app.test_client()

        with app.app_context():
            from app.models.competidor import Competidor
            from app.models.usuario import Usuario

            otro_admin = Usuario(email="otro@test.local", nombre="OTRO ADMIN",
                                 rol="admin", activo=True)
            otro_admin.set_password("secret123")
            db.session.add(otro_admin)
            db.session.commit()
            ajena = Competidor(nombre_completo="ANA GOMEZ", documento="1088123456",
                               club="OTRO DOJANG", activo=True,
                               created_by=otro_admin.id)
            db.session.add(ajena)
            db.session.commit()

        respuesta = _inscribir(cliente, token, primera, documento="1088123456")
        assert respuesta.status_code == 400
        error = respuesta.get_json()["error"]
        assert "Ya existe un competidor con documento" in error
        # Y sin decir de quién es: es de otro workspace.
        assert "registrado por otro administrador" in error

    def test_un_uid_que_no_es_suyo_no_existe(self, entorno):
        app, token, primera, _ = entorno
        cliente = app.test_client()

        with app.app_context():
            from app.models.competidor import Competidor
            from app.models.usuario import Usuario

            otro_admin = Usuario(email="otro2@test.local", nombre="OTRO ADMIN",
                                 rol="admin", activo=True)
            otro_admin.set_password("secret123")
            db.session.add(otro_admin)
            db.session.commit()
            ajena = Competidor(nombre_completo="LUZ MARINA", club="OTRO DOJANG",
                               activo=True, created_by=otro_admin.id)
            db.session.add(ajena)
            db.session.commit()
            uid_ajeno = ajena.uid

        respuesta = _inscribir(cliente, token, primera, uid=uid_ajeno)
        assert respuesta.status_code == 404
        assert not _fichas(app, "LUZ MARINA")[0].club == "DOJANG SUR"
