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

    # 403 con frase y no 404 (F5, punto 3): el campeonato activo ya es público,
    # así que decir que existe no revela nada, y «tu club no está invitado» sí
    # le dice al maestro qué hacer.
    r = _inscribir(cliente, tokens, ajeno.id)
    assert r.status_code == 403
    assert "no está invitado" in r.get_json()["error"]


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


# ── F5: el maestro invitado, con la red puesta ──────────────────────────────

CLUB_1 = "0c000000-0000-4000-8000-000000000001"


@pytest.fixture()
def invitado(pg):
    """Un admin con su campeonato, y un maestro del PORTAL (sin creado_por_id)."""
    app, db = pg
    from app.models.campeonato import Campeonato
    from app.models.usuario import Usuario

    admin = Usuario(email="admin@t.local", nombre="ADMIN", rol="admin", activo=True)
    admin.set_password("secret123")
    maestro = Usuario(email="portal@t.local", nombre="PORTAL", rol="maestro",
                      activo=True, org_id=CLUB_1)
    maestro.clubes = ["CLUB UNO"]
    maestro.set_password("secret123")
    db.session.add_all([admin, maestro])
    db.session.commit()
    camp = Campeonato(nombre="COPA", estado="preparacion", activo=True, created_by=admin.id)
    db.session.add(camp)
    db.session.commit()
    return app.test_client(), {"admin": _token(admin), "maestro": _token(maestro)}, camp.id


def test_el_maestro_invitado_inscribe_en_el_workspace_de_otro(invitado):
    """La puerta de F5 entera con RLS: sin `en_workspace` nada de esto se ve."""
    cliente, tokens, camp_id = invitado
    r = cliente.post(
        f"/api/campeonatos/{camp_id}/clubes",
        json={"org_id": CLUB_1, "nombre": "Club Uno"},
        headers=_h(tokens["admin"]),
    )
    assert r.status_code == 201, r.get_json()

    lista = cliente.get("/api/inscripciones/maestro/campeonatos", headers=_h(tokens["maestro"]))
    assert [c["acceso"] for c in lista.get_json()] == ["invitado"]

    r = cliente.post(
        f"/api/inscripciones/maestro/campeonato/{camp_id}",
        json={"competidor": {**ALUMNA, "club": "CLUB UNO"}, "peso": 40},
        headers=_h(tokens["maestro"]),
    )
    assert r.status_code == 201, r.get_json()
    ins_id = r.get_json()["inscripcion"]["id"]

    mias = cliente.get("/api/inscripciones/maestro/mias", headers=_h(tokens["maestro"]))
    assert len(mias.get_json()) == 1

    del_admin = cliente.get(f"/api/inscripciones/campeonato/{camp_id}", headers=_h(tokens["admin"]))
    assert [i["estado"] for i in del_admin.get_json()] == ["pendiente"]

    clubes = cliente.get(f"/api/campeonatos/{camp_id}/clubes", headers=_h(tokens["admin"]))
    assert [i["estado"] for i in clubes.get_json()] == ["aceptado"]

    # Rechazar y corregir, también con la red puesta.
    cliente.patch(f"/api/inscripciones/{ins_id}/estado",
                  json={"estado": "rechazada"}, headers=_h(tokens["admin"]))
    r = cliente.put(
        f"/api/inscripciones/maestro/{ins_id}",
        json={"competidor": {**ALUMNA, "club": "CLUB UNO"}, "peso": 41},
        headers=_h(tokens["maestro"]),
    )
    assert r.status_code == 200, r.get_json()

    alumnos = cliente.get(
        f"/api/inscripciones/maestro/alumnos?campeonato_id={camp_id}",
        headers=_h(tokens["maestro"]),
    )
    assert [a["nombre_completo"] for a in alumnos.get_json()] == ["ANA GOMEZ"]


def test_el_mismo_documento_en_dos_workspaces_ya_no_es_un_500(pg, club):
    """Era un 500: RLS escondía la ficha ajena y el INSERT chocaba con el índice."""
    app, db = pg
    cliente, tokens, camp_id = club
    assert _inscribir(cliente, tokens, camp_id).status_code == 201

    from app.models.usuario import Usuario

    _sembrar()
    otro = Usuario(email="otro@t.local", nombre="OTRO", rol="admin", activo=True)
    otro.set_password("secret123")
    db.session.add(otro)
    db.session.commit()

    r = cliente.post(
        "/api/competidores",
        json={**ALUMNA, "genero": "FEMENINO"},
        headers=_h(_token(otro)),
    )
    assert r.status_code == 201, r.get_json()


def test_la_migracion_del_documento_en_una_base_vieja(pg):
    """Una base de antes: índice ÚNICO sobre `documento` solo. El arranque lo cambia."""
    app, db = pg
    from sqlalchemy import inspect, text

    from app.schema_compat import _documento_unico_por_workspace

    db.session.execute(text("DROP INDEX IF EXISTS uq_competidores_workspace_documento"))
    db.session.execute(text("DROP INDEX IF EXISTS ix_competidores_documento"))
    db.session.execute(text("CREATE UNIQUE INDEX ix_competidores_documento ON competidores (documento)"))
    db.session.commit()

    _documento_unico_por_workspace({"competidores"})

    indices = {i["name"]: i for i in inspect(db.engine).get_indexes("competidores")}
    assert indices["ix_competidores_documento"]["unique"] is False
    assert indices["uq_competidores_workspace_documento"]["unique"] is True


def test_borrar_un_campeonato_con_invitaciones_en_postgres(invitado):
    """Las claves foráneas SÍ se cumplen aquí: la invitación no puede quedar colgando."""
    cliente, tokens, camp_id = invitado
    cliente.post(f"/api/campeonatos/{camp_id}/clubes",
                 json={"org_id": CLUB_1, "nombre": "Club Uno"}, headers=_h(tokens["admin"]))
    r = cliente.delete(f"/api/campeonatos/{camp_id}", headers=_h(tokens["admin"]))
    assert r.status_code == 200, r.get_json()


def test_otro_admin_no_pisa_resultados_publicados_ni_revienta(pg, club):
    """Era un 500 en PostgreSQL: RLS escondía el snapshot ajeno y el INSERT chocaba."""
    app, db = pg
    cliente, tokens, _ = club
    sobre = {
        "formato": "dinamyt-resultados", "version": 1,
        "export_uuid": "e0000000000000000000000000000001",
        "campeonato": {"nombre": "COPA"}, "resultados": [],
    }
    assert cliente.post("/api/resultados/importar", json=sobre,
                        headers=_h(tokens["admin"])).status_code == 200

    from app.models.usuario import Usuario

    _sembrar()
    otro = Usuario(email="otro@t.local", nombre="OTRO", rol="admin", activo=True)
    otro.set_password("secret123")
    db.session.add(otro)
    db.session.commit()
    r = cliente.post("/api/resultados/importar", json=sobre, headers=_h(_token(otro)))
    assert r.status_code == 409, r.get_json()


def test_otro_admin_no_publica_sobre_un_campeonato_ajeno_en_postgres(pg, club):
    """RLS le esconde el campeonato ajeno: la puerta tiene que verlo igual."""
    app, db = pg
    cliente, _, camp_id = club
    from app.models.campeonato import Campeonato
    from app.models.usuario import Usuario

    _sembrar()
    camp = db.session.get(Campeonato, camp_id)
    camp.export_uuid = "c0000000000000000000000000000002"
    otro = Usuario(email="otro2@t.local", nombre="OTRO", rol="admin", activo=True)
    otro.set_password("secret123")
    db.session.add(otro)
    db.session.commit()
    sobre = {
        "formato": "dinamyt-resultados", "version": 1,
        "export_uuid": camp.export_uuid,
        "campeonato": {"nombre": "FALSA"}, "resultados": [],
    }
    r = cliente.post("/api/resultados/importar", json=sobre, headers=_h(_token(otro)))
    assert r.status_code == 409, r.get_json()
    assert r.get_json()["motivo"] == "campeonato_de_otro"


# ══════════════════════════════════════════════════════════════════════════
#  nº 5 de la PARTE 4 (25 sep 2026): el correo es único en TODA la base
# ══════════════════════════════════════════════════════════════════════════

def _otro_admin_con_su_juez(db):
    from app.models.usuario import Usuario

    _sembrar()
    otro = Usuario(email="otro-admin@t.local", nombre="OTRO", rol="admin", activo=True)
    otro.set_password("secret123")
    db.session.add(otro)
    db.session.commit()
    juez = Usuario(email="juez-ajeno@t.local", nombre="JUEZ AJENO", rol="juez",
                   activo=True, creado_por_id=otro.id,
                   eco_sub="aa000000-0000-4000-8000-0000000000aa")
    juez.set_password("secret123")
    db.session.add(juez)
    db.session.commit()
    return otro, juez


def test_dar_de_alta_un_correo_de_otro_workspace_es_409_y_no_500(pg, club):
    """RLS escondía al usuario ajeno: el correo salía libre y el INSERT chocaba."""
    app, db = pg
    cliente, tokens, _ = club
    _otro_admin_con_su_juez(db)

    r = cliente.post("/api/auth/register", headers=_h(tokens["admin"]), json={
        "email": "juez-ajeno@t.local", "password": "secret123",
        "nombre": "Juez", "rol": "juez",
    })
    assert r.status_code == 409, r.get_json()


def test_cambiar_el_correo_al_de_otro_workspace_es_409_y_no_500(pg, club):
    app, db = pg
    cliente, tokens, _ = club
    _otro_admin_con_su_juez(db)
    from app.models.usuario import Usuario

    _sembrar()
    maestro_id = Usuario.query.filter_by(email="maestro@t.local").one().id
    r = cliente.put(f"/api/auth/users/{maestro_id}", headers=_h(tokens["admin"]),
                    json={"email": "juez-ajeno@t.local"})
    assert r.status_code == 409, r.get_json()


def test_el_alta_en_dinamyt_con_la_red_puesta(pg, club, monkeypatch):
    """El juez nace en el workspace del admin; un sub que ya es de otro, 409."""
    app, db = pg
    cliente, tokens, _ = club
    from app.api import auth as auth_api
    from app.models.usuario import Usuario

    _sembrar()
    admin = Usuario.query.filter_by(email="admin@t.local").one()
    admin.org_id = "0f000000-0000-4000-8000-00000000fede"
    db.session.commit()
    app.config["ECOSYSTEM_JWKS_URL"] = "https://id.ejemplo.invalid/auth/jwks"
    monkeypatch.setenv("ECOSYSTEM_SYNC_SECRET", "secreto")

    subs = iter(["aa000000-0000-4000-8000-0000000000b1", "aa000000-0000-4000-8000-0000000000aa"])
    monkeypatch.setattr(auth_api, "alta_de_juez_en_dinamyt",
                        lambda *a, **k: {"ecoSub": next(subs), "cuenta": "nueva", "invitacion": None})
    _otro_admin_con_su_juez(db)

    r = cliente.post("/api/auth/register", headers=_h(tokens["admin"]),
                     json={"email": "juez-nuevo@t.local", "nombre": "Juez Nuevo", "rol": "juez"})
    assert r.status_code == 201, r.get_json()
    lista = cliente.get("/api/auth/users", headers=_h(tokens["admin"])).get_json()
    nuevo = next(u for u in lista if u["email"] == "juez-nuevo@t.local")
    assert nuevo["cuenta_de_dinamyt"] is True
    assert nuevo["roles"] == ["juez"]

    # La misma cuenta de DINAMYT ya tiene espejo, en el workspace de otro admin.
    r = cliente.post("/api/auth/register", headers=_h(tokens["admin"]),
                     json={"email": "otro-correo@t.local", "nombre": "Juez", "rol": "juez"})
    assert r.status_code == 409, r.get_json()
    assert "juez-ajeno@t.local" in r.get_json()["error"]


# ══════════════════════════════════════════════════════════════════════════
#  Lo que quedaba del plan (25 sep 2026), con la red puesta
# ══════════════════════════════════════════════════════════════════════════

SUB_MAESTRO_PG = "22222222-2222-4222-8222-222222222222"
SUB_ALUMNA_PG = "44444444-4444-4444-8444-444444444444"


def test_el_maestro_inscribe_a_alguien_de_su_club_en_dinamyt(pg, club, monkeypatch):
    """Punto 2: la ficha nace ENLAZADA en el workspace del campeonato, y la
    lista de la gente del club ve su ficha y su inscripción con RLS."""
    app, db = pg
    cliente, tokens, camp_id = club
    from app.api import competidores as competidores_api
    from app.models.competidor import Competidor
    from app.models.usuario import Usuario

    _sembrar()
    maestro = Usuario.query.filter_by(email="maestro@t.local").one()
    maestro.eco_sub = SUB_MAESTRO_PG
    db.session.commit()
    miembro = {"sub": SUB_ALUMNA_PG, "fullName": "Luz Marina", "birthDate": "2012-05-04",
               "gender": "FEMENINO", "documentId": "2002", "club": {"id": "c", "name": "DOJANG SUR"}}
    monkeypatch.setattr(competidores_api, "miembros_del_club",
                        lambda sub, persona=None: [miembro] if persona in (None, SUB_ALUMNA_PG) else [])

    r = cliente.post(
        f"/api/inscripciones/maestro/campeonato/{camp_id}",
        json={"eco_sub": SUB_ALUMNA_PG, "competidor": {"club": "DOJANG SUR"}, "peso": 40},
        headers=_h(tokens["maestro"]),
    )
    assert r.status_code == 201, r.get_json()

    _sembrar()
    ficha = Competidor.query.filter_by(eco_sub=SUB_ALUMNA_PG).one()
    assert ficha.created_by == Usuario.query.filter_by(email="admin@t.local").one().id

    lista = cliente.get(f"/api/inscripciones/maestro/miembros?campeonato_id={camp_id}",
                        headers=_h(tokens["maestro"])).get_json()
    assert lista["miembros"][0]["ficha_uid"] == ficha.uid
    assert lista["miembros"][0]["inscrito"] is True


def test_solo_invitados_con_la_red_puesta(pg, club):
    """Punto 3: la invitación por nombre abre la casa; sin ella, 403."""
    app, db = pg
    cliente, tokens, camp_id = club

    r = cliente.put(f"/api/campeonatos/{camp_id}/clubes/solo-invitados",
                    json={"solo_invitados": True}, headers=_h(tokens["admin"]))
    assert r.status_code == 200, r.get_json()
    assert _inscribir(cliente, tokens, camp_id).status_code == 403

    r = cliente.post(f"/api/campeonatos/{camp_id}/clubes",
                     json={"nombre": "Dojang Sur"}, headers=_h(tokens["admin"]))
    assert r.status_code == 201, r.get_json()
    lista = cliente.get("/api/inscripciones/maestro/campeonatos", headers=_h(tokens["maestro"])).get_json()
    assert [c["id"] for c in lista] == [camp_id]
    assert _inscribir(cliente, tokens, camp_id).status_code == 201


def test_el_traspaso_con_la_red_puesta(pg, club):
    """Punto 4: el superadmin mueve el workspace, y el nuevo ve TODO —también
    las llaves y las fichas, que es lo que el `org_id` a secas no daba."""
    app, db = pg
    cliente, tokens, camp_id = club
    from app.models.llave import Llave
    from app.models.usuario import Usuario

    assert _inscribir(cliente, tokens, camp_id).status_code == 201
    _sembrar()
    viejo = Usuario.query.filter_by(email="admin@t.local").one()
    viejo.org_id = "0f000000-0000-4000-8000-00000000fede"
    nuevo = Usuario(email="nuevo@t.local", nombre="NUEVO", rol="admin", activo=True,
                    org_id=viejo.org_id)
    nuevo.set_password("secret123")
    jefe = Usuario(email="super@t.local", nombre="SUPER", rol="admin", activo=True,
                   es_superadmin=True)
    jefe.set_password("secret123")
    db.session.add_all([nuevo, jefe])
    db.session.flush()
    db.session.add(Llave(campeonato_id=camp_id, tipo="combate", nombre="L",
                         created_by=viejo.id, estructura={"competidores": []}))
    db.session.commit()

    r = cliente.post("/api/auth/organizaciones/traspasar",
                     json={"de": viejo.id, "a": nuevo.id, "aplicar": True},
                     headers=_h(_token(jefe)))
    assert r.status_code == 200, r.get_json()

    del_nuevo = cliente.get("/api/campeonatos", headers=_h(_token(nuevo))).get_json()
    assert [c["id"] for c in del_nuevo] == [camp_id]
    llaves = cliente.get(f"/api/llaves/campeonato/{camp_id}", headers=_h(_token(nuevo)))
    assert llaves.status_code == 200, llaves.get_json()
    assert len(llaves.get_json()) == 1
    inscritos = cliente.get(f"/api/inscripciones/campeonato/{camp_id}", headers=_h(_token(nuevo)))
    assert len(inscritos.get_json()) == 1
    # Y el maestro que era del viejo ahora es de la casa del nuevo.
    assert cliente.get("/api/inscripciones/maestro/campeonatos",
                       headers=_h(tokens["maestro"])).get_json()[0]["acceso"] == "casa"
