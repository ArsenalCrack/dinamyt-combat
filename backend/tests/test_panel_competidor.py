"""
El alumno entra: su panel (F3 de `PLAN-CAMPEONATOS.md`, parte 3).

Lo que se prueba, en orden:

  1. El pase de un alumno crea su espejo como competidor — y `sin_consola`
     sigue siendo la respuesta para quien no tiene NINGÚN papel.
  2. Reclamar la ficha: con documento y fecha, sin pisar a nadie, con tope.
  3. `/api/mi/panel` enseña lo de la persona de la sesión, y nada más.
  4. Los resultados (opción B): lo enlazado es exacto, lo viejo sale «sin
     confirmar», y un homónimo enlazado a OTRA ficha no es tuyo.
  5. El administrador enlaza y desenlaza a mano, a la vista.
"""

import sys
import time
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jwt  # noqa: E402
import pytest  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

from app import create_app, espejo, identidad  # noqa: E402
from app.config import DevelopmentConfig  # noqa: E402
from app.extensions import db  # noqa: E402

DevelopmentConfig.SQLALCHEMY_DATABASE_URI = "sqlite://"

LLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
SUB_ANA = "aa000000-0000-4000-8000-0000000000a1"
SUB_LUZ = "aa000000-0000-4000-8000-0000000000b2"


def _cabecera(user):
    from flask_jwt_extended import create_access_token

    token = create_access_token(
        identity=str(user.id),
        additional_claims={"rol": user.rol, "nombre": user.nombre, "email": user.email},
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setattr(identidad, "_llave_del_pase", lambda token, url: LLAVE.public_key())
    # El club se pregunta al ecosistema por la red: aquí no importa.
    monkeypatch.setattr(espejo, "club_del_pase", lambda claims, pase: None)
    aplicacion = create_app("development")
    aplicacion.config["ECOSYSTEM_JWKS_URL"] = "https://ejemplo.invalid/auth/jwks"
    with aplicacion.app_context():
        db.create_all()
        yield aplicacion
        db.session.remove()
        db.drop_all()


def pase(rol="competitor", roles=None, sub=SUB_ANA, email="ana@dinamyt.org"):
    ahora = int(time.time())
    cuerpo = {
        "sub": sub,
        "email": email,
        "fullName": "Ana Gómez",
        "iss": identidad.EMISOR_ECOSYSTEM,
        "iat": ahora,
        "exp": ahora + 1800,
        "app_scopes": ["campeonatos"],
        "role_campeonatos": rol,
    }
    if roles is not None:
        cuerpo["roles_campeonatos"] = roles
    return jwt.encode(cuerpo, LLAVE, algorithm="RS256")


def canjear(cliente, token):
    return cliente.post("/api/auth/sesion", headers={"Authorization": f"Bearer {token}"})


@pytest.fixture()
def mundo(app):
    """Dos administradores, un maestro, dos alumnas con cuenta y tres fichas.

    · ANA tiene cuenta pero su ficha todavía no está enlazada.
    · LUZ ya tiene la suya enlazada.
    · PAULA no tiene fecha de nacimiento: no se puede reclamar sola.
    """
    from app.models.campeonato import Campeonato
    from app.models.competidor import Competidor, Inscripcion
    from app.models.usuario import Usuario

    admin = Usuario(email="admin@t.local", nombre="ADMIN", rol="admin", activo=True)
    otro_admin = Usuario(email="otro@t.local", nombre="OTRO", rol="admin", activo=True)
    for u in (admin, otro_admin):
        u.set_password("secret123")
        db.session.add(u)
    db.session.commit()

    maestro = Usuario(email="maestro@t.local", nombre="MAESTRO SUR", rol="maestro",
                      activo=True, creado_por_id=admin.id)
    maestro.clubes = ["DOJANG SUR"]
    ana = Usuario(email="ana@dinamyt.org", nombre="ANA GÓMEZ", rol="competidor",
                  activo=True, eco_sub=SUB_ANA)
    luz = Usuario(email="luz@dinamyt.org", nombre="LUZ MARINA", rol="competidor",
                  activo=True, eco_sub=SUB_LUZ)
    # Creado a mano en el modo local: no viene del portal.
    local = Usuario(email="local@t.local", nombre="SIN CUENTA", rol="juez",
                    activo=True, creado_por_id=admin.id)
    for u in (maestro, ana, luz, local):
        u.set_password("secret123")
        db.session.add(u)
    db.session.commit()

    camp = Campeonato(nombre="COPA SUR", activo=True, estado="preparacion",
                      fecha_inicio=date.today() + timedelta(days=20), created_by=admin.id)
    ajeno = Campeonato(nombre="COPA NORTE", activo=True, estado="finalizado",
                       fecha_inicio=date(2025, 5, 1), created_by=otro_admin.id)
    db.session.add_all([camp, ajeno])
    db.session.flush()

    ficha_ana = Competidor(nombre_completo="ANA GÓMEZ", documento="1001",
                           fecha_nacimiento=date(2010, 4, 2), club="DOJANG SUR",
                           activo=True, created_by=admin.id)
    ficha_luz = Competidor(nombre_completo="LUZ MARINA", documento="2002",
                           fecha_nacimiento=date(2011, 7, 9), club="DOJANG SUR",
                           activo=True, created_by=admin.id, eco_sub=SUB_LUZ)
    sin_fecha = Competidor(nombre_completo="PAULA RÍOS", documento="3003",
                           club="DOJANG SUR", activo=True, created_by=admin.id)
    db.session.add_all([ficha_ana, ficha_luz, sin_fecha])
    db.session.flush()

    db.session.add(Inscripcion(campeonato_id=camp.id, competidor_id=ficha_ana.id,
                               modalidades=["COMBATE"], estado="pendiente",
                               created_by=maestro.id))
    db.session.add(Inscripcion(campeonato_id=camp.id, competidor_id=ficha_luz.id,
                               modalidades=["COMBATE"], estado="rechazada",
                               motivo_rechazo="Falta el peso", created_by=maestro.id))
    db.session.commit()

    return SimpleNamespace(
        cliente=app.test_client(),
        admin=admin, otro_admin=otro_admin, maestro=maestro,
        ana=ana, luz=luz, local=local,
        camp_id=camp.id, ajeno_id=ajeno.id, export_uuid=camp.export_uuid,
        ficha_luz={"id": ficha_luz.id, "uid": ficha_luz.uid},
        sin_fecha_id=sin_fecha.id,
    )


def _panel(m, quien):
    res = m.cliente.get("/api/mi/panel", headers=_cabecera(quien))
    assert res.status_code == 200, res.get_json()
    return res.get_json()


def _reclamar(m, quien, documento, fecha):
    return m.cliente.post("/api/mi/ficha/reclamar", headers=_cabecera(quien),
                          json={"documento": documento, "fecha_nacimiento": fecha})


# ══════════════════════════════════════════════════════════════════════════
#  1 · El alumno entra
# ══════════════════════════════════════════════════════════════════════════

class TestElAlumnoEntra:
    def test_nace_su_espejo_como_competidor(self, app):
        from app.models.usuario import Usuario

        res = canjear(app.test_client(), pase())

        assert res.status_code == 200
        assert res.get_json()["user"]["rol"] == "competidor"
        fila = Usuario.query.filter_by(email="ana@dinamyt.org").one()
        assert fila.roles == ["competidor"]
        assert fila.eco_sub == SUB_ANA

    def test_student_es_lo_mismo(self, app):
        res = canjear(app.test_client(), pase(rol="student"))
        assert res.get_json()["user"]["rol"] == "competidor"

    def test_sin_ningun_papel_sigue_siendo_sin_consola(self, app):
        from app.models.usuario import Usuario

        res = canjear(app.test_client(), pase(rol=None))

        assert res.status_code == 403
        assert res.get_json()["motivo"] == "sin_consola"
        assert Usuario.query.count() == 0

    def test_si_despues_le_dan_juez_cambia_de_pantalla_sin_perder_el_panel(self, app):
        cliente = app.test_client()
        canjear(cliente, pase())

        res = canjear(cliente, pase(rol="judge", roles=["judge", "competitor"]))

        assert res.get_json()["user"]["rol"] == "juez"
        assert res.get_json()["user"]["roles"] == ["juez", "competidor"]

    def test_con_su_sesion_no_lee_lo_del_personal(self, mundo):
        res = mundo.cliente.get(f"/api/llaves/campeonato/{mundo.camp_id}",
                                headers=_cabecera(mundo.ana))
        assert res.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  2 · Reclamar la ficha
# ══════════════════════════════════════════════════════════════════════════

class TestReclamarLaFicha:
    def test_con_documento_y_fecha_queda_enlazada(self, mundo):
        from app.models.competidor import Competidor

        # Con puntos, como se escribe una cédula: se aceptan igual que al crearla.
        res = _reclamar(mundo, mundo.ana, "1.001", "2010-04-02")

        assert res.status_code == 200, res.get_json()
        assert Competidor.query.filter_by(documento="1001").one().eco_sub == SUB_ANA
        assert [f["documento"] for f in _panel(mundo, mundo.ana)["fichas"]] == ["1001"]

    def test_la_fecha_equivocada_contesta_igual_que_un_documento_que_no_existe(self, mundo):
        # Distinguirlas le diría a cualquiera qué documentos están registrados.
        mala = _reclamar(mundo, mundo.ana, "1001", "2010-04-03")
        inexistente = _reclamar(mundo, mundo.ana, "999999", "2010-04-02")

        assert mala.status_code == inexistente.status_code == 404
        assert mala.get_json() == inexistente.get_json()

    def test_una_ficha_sin_fecha_no_se_reclama_sola(self, mundo):
        # Con solo el documento bastaría con conocer la cédula de alguien.
        assert _reclamar(mundo, mundo.ana, "3003", "2010-04-02").status_code == 404

    def test_no_se_pisa_la_ficha_de_otra_cuenta(self, mundo):
        from app.models.competidor import Competidor

        res = _reclamar(mundo, mundo.ana, "2002", "2011-07-09")

        assert res.status_code == 409
        assert res.get_json()["motivo"] == "ficha_ocupada"
        assert Competidor.query.filter_by(documento="2002").one().eco_sub == SUB_LUZ

    def test_reclamar_otra_vez_la_propia_no_falla(self, mundo):
        assert _reclamar(mundo, mundo.luz, "2002", "2011-07-09").status_code == 200

    def test_tiene_tope_aunque_al_final_acierte(self, mundo):
        for _ in range(5):
            assert _reclamar(mundo, mundo.ana, "1001", "1999-01-01").status_code == 404
        assert _reclamar(mundo, mundo.ana, "1001", "2010-04-02").status_code == 429

    def test_un_formato_mal_escrito_no_gasta_intentos(self, mundo):
        for _ in range(6):
            assert _reclamar(mundo, mundo.ana, "abc", "2010-04-02").status_code == 400
        assert _reclamar(mundo, mundo.ana, "1001", "2010-04-02").status_code == 200

    def test_sin_cuenta_de_dinamyt_no_hay_a_quien_enlazar(self, mundo):
        res = _reclamar(mundo, mundo.local, "1001", "2010-04-02")
        assert res.status_code == 409
        assert res.get_json()["motivo"] == "sin_cuenta"

    def test_quien_reclama_compite_aunque_su_pase_no_lo_dijera(self, mundo):
        from app.models.usuario import Usuario

        mundo.maestro.eco_sub = "aa000000-0000-4000-8000-0000000000c3"
        db.session.commit()

        assert _reclamar(mundo, mundo.maestro, "1001", "2010-04-02").status_code == 200

        db.session.expire_all()
        fila = db.session.get(Usuario, mundo.maestro.id)
        # Sigue entrando a SU consola; el panel es un papel más.
        assert fila.rol == "maestro"
        assert fila.roles == ["maestro", "competidor"]


# ══════════════════════════════════════════════════════════════════════════
#  3 · El panel
# ══════════════════════════════════════════════════════════════════════════

class TestElPanel:
    def test_sin_ficha_esta_vacio(self, mundo):
        panel = _panel(mundo, mundo.ana)
        assert panel["persona"]["con_cuenta"] is True
        assert panel["fichas"] == []
        assert panel["inscripciones"] == []
        assert panel["resultados"] == []

    def test_sin_cuenta_lo_dice(self, mundo):
        assert _panel(mundo, mundo.local)["persona"]["con_cuenta"] is False

    def test_ensena_lo_de_la_sesion_y_nada_mas(self, mundo):
        res = mundo.cliente.get("/api/mi/panel?eco_sub=" + SUB_ANA, headers=_cabecera(mundo.luz))
        panel = res.get_json()
        assert [f["documento"] for f in panel["fichas"]] == ["2002"]
        assert "1001" not in res.get_data(as_text=True)

    def test_sin_sesion_no_hay_panel(self, mundo):
        assert mundo.cliente.get("/api/mi/panel").status_code == 401

    def test_la_inscripcion_con_su_estado_su_motivo_y_su_maestro(self, mundo):
        panel = _panel(mundo, mundo.luz)
        (ins,) = panel["inscripciones"]
        assert ins["estado"] == "rechazada"
        assert ins["motivo_rechazo"] == "Falta el peso"
        assert ins["maestro"] == {"nombre": "MAESTRO SUR", "club": "DOJANG SUR"}
        assert panel["maestro"]["nombre"] == "MAESTRO SUR"

    def test_una_inscripcion_rechazada_no_es_un_campeonato_proximo(self, mundo):
        assert _panel(mundo, mundo.luz)["proximos"] == []

    def test_una_pendiente_si(self, mundo):
        _reclamar(mundo, mundo.ana, "1001", "2010-04-02")
        assert [c["nombre"] for c in _panel(mundo, mundo.ana)["proximos"]] == ["COPA SUR"]


# ══════════════════════════════════════════════════════════════════════════
#  4 · Los resultados
# ══════════════════════════════════════════════════════════════════════════

def _final(camp_id, uno, dos, ganador=1, nombre="COMBATE -45KG"):
    """Una llave de combate de dos, ya terminada."""
    from app.models.llave import Llave

    estructura = {
        "competidores": [uno, dos],
        "rondas": [[{"comp1": uno, "comp2": dos, "ganador": ganador}]],
        "campeon": uno if ganador == 1 else dos,
    }
    db.session.add(Llave(campeonato_id=camp_id, tipo="combate", nombre=nombre,
                         estado="terminada", estructura=estructura))
    db.session.commit()


RIVAL = {"id": 2, "nombre": "RIVAL", "club": "DOJANG NORTE"}


class TestLosResultados:
    def test_un_podio_enlazado_es_exacto(self, mundo):
        luz = {"id": 1, "nombre": "LUZ MARINA", "club": "DOJANG SUR",
               "competidor_uid": mundo.ficha_luz["uid"]}
        _final(mundo.camp_id, luz, RIVAL)

        panel = _panel(mundo, mundo.luz)

        (r,) = panel["resultados"]
        assert (r["tipo"], r["puesto"], r["medalla"], r["confirmado"]) == ("combate", 1, "oro", True)
        st = panel["estadisticas"]
        assert (st["combates"], st["victorias"], st["derrotas"]) == (1, 1, 0)
        assert st["medallas"] == {"oro": 1, "plata": 0, "bronce": 0}
        assert st["sin_confirmar"] == 0

    def test_un_homonimo_enlazado_a_otra_ficha_no_es_tuyo(self, mundo):
        impostora = {"id": 1, "nombre": "LUZ MARINA", "club": "DOJANG SUR",
                     "competidor_uid": "uid-de-otra-persona"}
        _final(mundo.camp_id, impostora, RIVAL)

        panel = _panel(mundo, mundo.luz)

        assert panel["resultados"] == []
        assert panel["estadisticas"]["combates"] == 0

    def test_una_llave_vieja_sin_enlace_sale_sin_confirmar(self, mundo):
        # Escrito distinto a propósito: tildes, mayúsculas y espacios no cuentan.
        vieja = {"id": 1, "nombre": "Luz  Marina", "club": "dojang sur"}
        _final(mundo.camp_id, RIVAL, vieja)

        panel = _panel(mundo, mundo.luz)

        (r,) = panel["resultados"]
        assert (r["puesto"], r["medalla"], r["confirmado"]) == (2, "plata", False)
        assert panel["estadisticas"]["derrotas"] == 1
        # El podio y el combate: los dos salieron por nombre.
        assert panel["estadisticas"]["sin_confirmar"] == 2

    def test_por_nombre_pero_de_otro_club_no_es_tuyo(self, mundo):
        otra = {"id": 1, "nombre": "LUZ MARINA", "club": "DOJANG ESTE"}
        _final(mundo.camp_id, otra, RIVAL)
        assert _panel(mundo, mundo.luz)["resultados"] == []

    def test_no_se_busca_por_nombre_donde_no_estas_inscrita(self, mundo):
        vieja = {"id": 1, "nombre": "LUZ MARINA", "club": "DOJANG SUR"}
        _final(mundo.ajeno_id, vieja, RIVAL)
        assert _panel(mundo, mundo.luz)["resultados"] == []

    def test_un_pase_directo_no_es_un_combate(self, mundo):
        from app.models.llave import Llave

        luz = {"id": 1, "nombre": "LUZ MARINA", "club": "DOJANG SUR",
               "competidor_uid": mundo.ficha_luz["uid"]}
        db.session.add(Llave(campeonato_id=mundo.camp_id, tipo="combate", nombre="SOLA",
                             estado="pendiente", estructura={
                                 "competidores": [luz],
                                 "rondas": [[{"comp1": luz, "comp2": None, "ganador": 1}]],
                             }))
        db.session.commit()

        assert _panel(mundo, mundo.luz)["estadisticas"]["combates"] == 0

    def test_figuras_sale_del_ranking_guardado(self, mundo):
        from app.models.categoria import Categoria
        from app.models.combate import Combate
        from app.models.tatami import SesionTatami, Tatami

        categoria = Categoria(nombre="FIGURAS", slug="figuras-panel")
        tatami = Tatami(campeonato_id=mundo.camp_id, numero=1)
        db.session.add_all([categoria, tatami])
        db.session.flush()
        sesion = SesionTatami(tatami_id=tatami.id, categoria_id=categoria.id)
        db.session.add(sesion)
        db.session.flush()
        db.session.add(Combate(sesion_tatami_id=sesion.id, ronda_final="figuras", jueces_detalle={
            "tipo": "figuras",
            "nombre_categoria": "FIGURA CON ARMAS",
            "ranking": [
                {"puesto": 1, "nombre": "RIVAL", "club": "DOJANG NORTE", "total": 9.1},
                {"puesto": 2, "nombre": "LUZ MARINA", "club": "DOJANG SUR", "total": 8.7,
                 "competidor_uid": mundo.ficha_luz["uid"]},
            ],
        }))
        db.session.commit()

        (r,) = _panel(mundo, mundo.luz)["resultados"]

        assert (r["tipo"], r["categoria"], r["puesto"], r["confirmado"]) == (
            "figuras", "FIGURA CON ARMAS", 2, True,
        )

    def test_lo_importado_con_enlace_sale_confirmado(self, mundo):
        # Desde el 25 sep 2026 el archivo del PC del evento lleva el uid de
        # cada puesto: lo tuyo es tuyo, no «alguien que se llama como tú».
        from app.models.resultado_publicado import ResultadoPublicado

        db.session.add(ResultadoPublicado(
            export_uuid=mundo.export_uuid, nombre="COPA SUR",
            payload={"resultados": [{
                "tipo": "combate", "nombre": "COMBATE -45KG",
                "podio": [
                    {"puesto": 1, "nombre": "RIVAL", "club": "DOJANG NORTE",
                     "competidor_uid": "otra-ficha"},
                    {"puesto": 3, "nombre": "LUZ MARINA", "club": "DOJANG SUR",
                     "competidor_uid": mundo.ficha_luz["uid"]},
                ],
            }]},
        ))
        db.session.commit()

        (r,) = _panel(mundo, mundo.luz)["resultados"]

        assert (r["puesto"], r["medalla"], r["confirmado"]) == (3, "bronce", True)

    def test_un_homonimo_con_otro_enlace_no_es_tuyo(self, mundo):
        from app.models.resultado_publicado import ResultadoPublicado

        db.session.add(ResultadoPublicado(
            export_uuid=mundo.export_uuid, nombre="COPA SUR",
            payload={"resultados": [{
                "tipo": "combate", "nombre": "COMBATE -45KG",
                "podio": [{"puesto": 1, "nombre": "LUZ MARINA", "club": "DOJANG SUR",
                           "competidor_uid": "la-de-otra-persona"}],
            }]},
        ))
        db.session.commit()

        assert _panel(mundo, mundo.luz)["resultados"] == []

    def test_lo_importado_del_modo_local_sale_por_nombre(self, mundo):
        # Un archivo anterior al 25 sep 2026 (o una llave hecha a mano) llega
        # sin enlace: se busca por nombre y se dice que es aproximado.
        from app.models.resultado_publicado import ResultadoPublicado

        db.session.add(ResultadoPublicado(
            export_uuid=mundo.export_uuid, nombre="COPA SUR",
            payload={"resultados": [{
                "tipo": "combate", "nombre": "COMBATE -45KG",
                "podio": [
                    {"puesto": 1, "nombre": "RIVAL", "club": "DOJANG NORTE"},
                    {"puesto": 3, "nombre": "LUZ MARINA", "club": "DOJANG SUR"},
                ],
            }]},
        ))
        db.session.commit()

        (r,) = _panel(mundo, mundo.luz)["resultados"]

        assert (r["puesto"], r["medalla"], r["confirmado"]) == (3, "bronce", False)


# ══════════════════════════════════════════════════════════════════════════
#  5 · El administrador enlaza a mano
# ══════════════════════════════════════════════════════════════════════════

def _enlazar(m, quien, comp_id, email):
    return m.cliente.put(f"/api/competidores/{comp_id}/cuenta",
                         headers=_cabecera(quien), json={"email": email})


class TestElAdministradorEnlaza:
    def test_por_el_correo_de_quien_ya_entro(self, mundo):
        res = _enlazar(mundo, mundo.admin, mundo.sin_fecha_id, "ana@dinamyt.org")

        assert res.status_code == 200, res.get_json()
        assert res.get_json()["competidor"]["cuenta_enlazada"] is True
        assert [f["documento"] for f in _panel(mundo, mundo.ana)["fichas"]] == ["3003"]

    def test_a_quien_nunca_entro_no(self, mundo):
        assert _enlazar(mundo, mundo.admin, mundo.sin_fecha_id, "nadie@dinamyt.org").status_code == 404

    def test_a_una_cuenta_que_no_viene_de_dinamyt_tampoco(self, mundo):
        assert _enlazar(mundo, mundo.admin, mundo.sin_fecha_id, "local@t.local").status_code == 404

    def test_no_se_pisa_y_se_desenlaza_a_la_vista(self, mundo):
        comp_id = mundo.ficha_luz["id"]
        assert _enlazar(mundo, mundo.admin, comp_id, "ana@dinamyt.org").status_code == 409

        res = mundo.cliente.delete(f"/api/competidores/{comp_id}/cuenta",
                                   headers=_cabecera(mundo.admin))

        assert res.status_code == 200
        assert _panel(mundo, mundo.luz)["fichas"] == []
        assert _enlazar(mundo, mundo.admin, comp_id, "ana@dinamyt.org").status_code == 200

    def test_solo_el_administrador_de_esa_ficha(self, mundo):
        assert _enlazar(mundo, mundo.maestro, mundo.sin_fecha_id, "ana@dinamyt.org").status_code == 403
        assert _enlazar(mundo, mundo.otro_admin, mundo.sin_fecha_id, "ana@dinamyt.org").status_code == 404

    def test_el_listado_dice_si_esta_enlazada_pero_no_a_quien(self, mundo):
        res = mundo.cliente.get("/api/competidores", headers=_cabecera(mundo.admin))

        por_documento = {c["documento"]: c for c in res.get_json()}
        assert por_documento["2002"]["cuenta_enlazada"] is True
        assert por_documento["1001"]["cuenta_enlazada"] is False
        assert SUB_LUZ not in res.get_data(as_text=True)


def test_editar_a_un_competidor_sin_tocarle_el_rol_no_falla(mundo):
    """La pantalla de usuarios manda el rol siempre, aunque no cambie.

    `competidor` no es un rol que reparta la consola, pero reenviar el que ya
    tiene no es repartirlo: sin esto, corregirle el nombre daba 400.
    """
    mundo.admin.es_superadmin = True
    db.session.commit()

    res = mundo.cliente.put(f"/api/auth/users/{mundo.ana.id}", headers=_cabecera(mundo.admin),
                            json={"nombre": "ana maría gómez", "rol": "competidor"})

    assert res.status_code == 200, res.get_json()
    assert res.get_json()["user"]["rol"] == "competidor"
    assert res.get_json()["user"]["nombre"] == "ANA MARÍA GÓMEZ"
