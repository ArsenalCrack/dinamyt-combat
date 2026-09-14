"""
La puerta del personal (F3 de `PLAN-CAMPEONATOS.md`, parte 1).

Hasta F3, tener sesión aquí y ser personal eran lo mismo: el pase de un alumno
no creaba fila. Por eso muchas lecturas se escribieron filtrando solo «si es
admin», y todo el que llegaba era de la casa. F3 deja entrar al competidor, y
el plan lo dice claro: *antes de desplegar hay que repasar los endpoints uno a
uno*. Esto es ese repaso, fijado:

  · Las lecturas del personal no las ve quien SOLO compite.
  · Las dos que enseñan fichas con documento y fecha de nacimiento son solo del
    administrador — y eso ya era un hueco HOY: un maestro o un juez recibía las
    fichas de todos los workspaces.
  · El juez sigue leyendo lo que su panel necesita.
  · Lo público sigue siendo público.
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


@pytest.fixture()
def puerta():
    app = create_app("development")
    with app.app_context():
        db.create_all()
        from app.models.campeonato import Campeonato
        from app.models.competidor import Competidor
        from app.models.llave import Llave
        from app.models.tatami import Tatami
        from app.models.usuario import Usuario

        admin = Usuario(email="admin@t.local", nombre="ADMIN", rol="admin", activo=True)
        otro_admin = Usuario(email="otro@t.local", nombre="OTRO", rol="admin", activo=True)
        for u in (admin, otro_admin):
            u.set_password("secret123")
            db.session.add(u)
        db.session.commit()

        maestro = Usuario(email="maestro@t.local", nombre="MAESTRO", rol="maestro",
                          activo=True, creado_por_id=admin.id)
        maestro.clubes = ["DOJANG SUR"]
        juez = Usuario(email="juez@t.local", nombre="JUEZ", rol="juez",
                       activo=True, creado_por_id=admin.id)
        # Así nace el espejo de un alumno desde F3: solo compite.
        alumno = Usuario(email="alumno@t.local", nombre="ALUMNA", rol="competidor", activo=True)
        de_baja = Usuario(email="baja@t.local", nombre="DE BAJA", rol="juez",
                          activo=False, creado_por_id=admin.id)
        for u in (maestro, juez, alumno, de_baja):
            u.set_password("secret123")
            db.session.add(u)
        db.session.commit()

        camp = Campeonato(nombre="COPA", estado="preparacion", activo=True, created_by=admin.id)
        db.session.add(camp)
        db.session.flush()
        tatami = Tatami(campeonato_id=camp.id, numero=1, activo=True)
        db.session.add(tatami)
        db.session.flush()
        llave = Llave(
            campeonato_id=camp.id, tatami_id=tatami.id, tipo="combate", nombre="LLAVE",
            descripcion="", estado="pendiente", seccion_clave="x", created_by=admin.id,
            estructura={"competidores": [{"nombre": "ANA", "club": "SUR"}]},
        )
        mia = Competidor(nombre_completo="ANA GOMEZ", documento="111", activo=True,
                         created_by=admin.id)
        ajena = Competidor(nombre_completo="LUZ MARINA", documento="222", activo=True,
                           created_by=otro_admin.id)
        db.session.add_all([llave, mia, ajena])
        db.session.commit()

        tokens = {n: _token(u) for n, u in {
            "admin": admin, "maestro": maestro, "juez": juez,
            "alumno": alumno, "de_baja": de_baja,
        }.items()}
        ids = {"camp": camp.id, "tatami": tatami.id, "llave": llave.id}
        yield app.test_client(), tokens, ids
        db.session.remove()
        db.drop_all()


def _get(cliente, tokens, quien, ruta, ids):
    return cliente.get(ruta.format(**ids), headers={"Authorization": f"Bearer {tokens[quien]}"})


# Lo que lee el personal. El juez tiene que seguir pudiendo.
DEL_PERSONAL = [
    "/api/campeonatos/{camp}",
    "/api/llaves/campeonato/{camp}",
    "/api/llaves/tatami/{tatami}",
    "/api/llaves/{llave}",
    "/api/tatamis/campeonato/{camp}",
    "/api/tatamis/{tatami}",
    "/api/combates/tatami/{tatami}",
    "/api/combates/recientes",
]

# Lo que enseña fichas con documento y fecha de nacimiento.
SOLO_DEL_ADMIN = [
    "/api/competidores",
    "/api/inscripciones/campeonato/{camp}",
]


@pytest.mark.parametrize("ruta", DEL_PERSONAL + SOLO_DEL_ADMIN)
def test_quien_solo_compite_no_lee_lo_del_personal(puerta, ruta):
    cliente, tokens, ids = puerta
    assert _get(cliente, tokens, "alumno", ruta, ids).status_code == 403


@pytest.mark.parametrize("ruta", DEL_PERSONAL)
def test_el_juez_sigue_leyendo_lo_de_su_panel(puerta, ruta):
    cliente, tokens, ids = puerta
    assert _get(cliente, tokens, "juez", ruta, ids).status_code == 200


@pytest.mark.parametrize("ruta", DEL_PERSONAL)
def test_un_usuario_dado_de_baja_tampoco_lee(puerta, ruta):
    cliente, tokens, ids = puerta
    assert _get(cliente, tokens, "de_baja", ruta, ids).status_code == 403


@pytest.mark.parametrize("quien", ["maestro", "juez"])
@pytest.mark.parametrize("ruta", SOLO_DEL_ADMIN)
def test_las_fichas_con_documento_son_solo_del_admin(puerta, quien, ruta):
    # ESTE era el hueco de hoy: antes cualquier sesión que no fuera admin
    # recibía las fichas de TODOS los workspaces, sin filtro.
    cliente, tokens, ids = puerta
    assert _get(cliente, tokens, quien, ruta, ids).status_code == 403


def test_el_admin_ve_sus_fichas_y_no_las_de_otro(puerta):
    cliente, tokens, ids = puerta
    res = _get(cliente, tokens, "admin", "/api/competidores", ids)
    assert res.status_code == 200
    nombres = {c["nombre_completo"] for c in res.get_json()}
    assert nombres == {"ANA GOMEZ"}


def test_el_admin_sigue_viendo_las_inscripciones_de_su_campeonato(puerta):
    cliente, tokens, ids = puerta
    assert _get(cliente, tokens, "admin", "/api/inscripciones/campeonato/{camp}", ids).status_code == 200


def test_la_guarda_va_antes_de_confirmar_que_algo_existe(puerta):
    # Un campeonato que no existe tiene que dar lo MISMO que uno que existe.
    cliente, tokens, ids = puerta
    assert _get(cliente, tokens, "alumno", "/api/campeonatos/999999", ids).status_code == 403
    assert _get(cliente, tokens, "maestro", "/api/inscripciones/campeonato/999999", ids).status_code == 403


def test_lo_publico_sigue_siendo_publico(puerta):
    cliente, _, _ = puerta
    assert cliente.get("/api/campeonatos/publico").status_code == 200
    assert cliente.get("/api/resultados/campeonatos").status_code == 200
