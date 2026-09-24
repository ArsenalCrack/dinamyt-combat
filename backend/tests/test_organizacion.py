"""
La organización llega a Campeonatos (F4 de `PLAN-CAMPEONATOS.md`).

Lo que se defiende aquí, en orden:

  1. **La organización del pase se copia a la fila** en cada entrada, y el
     nombre se pregunta UNA vez. Sin `org_id` en el pase no se borra nada.
  2. **Un solo administrador por organización** — al CREAR el espejo. El
     segundo entra sin el papel de admin, y a nadie que ya estaba se le quita
     nada (D3).
  3. **El campeonato lleva la organización de quien lo crea**, y los de antes
     la reciben en cuanto se sabe la de su creador.
  4. **El informe** de las organizaciones con más de un admin, solo para el
     superadministrador.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jwt  # noqa: E402
import pytest  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

from app import create_app, espejo, identidad  # noqa: E402
from app.config import DevelopmentConfig  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models.campeonato import Campeonato  # noqa: E402
from app.models.usuario import Usuario  # noqa: E402

DevelopmentConfig.SQLALCHEMY_DATABASE_URI = "sqlite://"

LLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
ORG_FEDE = "0f000000-0000-4000-8000-00000000fede"
ORG_CLUB = "0f000000-0000-4000-8000-00000000c1ab"


@pytest.fixture()
def app():
    aplicacion = create_app("development")
    with aplicacion.app_context():
        db.create_all()
        yield aplicacion
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def preguntas(monkeypatch):
    """Cuántas veces se le pregunta al ecosistema, y qué contesta."""
    registro = {"veces": 0, "nombres": {ORG_FEDE: "FEDERACIÓN DEL VALLE", ORG_CLUB: "DOJANG SUR"}}

    def falso(claims, pase):
        registro["veces"] += 1
        nombre = registro["nombres"].get(claims.get("org_id"))
        return {"nombre": nombre, "ciudad": "Cali", "pais": "Colombia"} if nombre else None

    monkeypatch.setattr(espejo, "club_del_pase", falso)
    return registro


@pytest.fixture()
def cliente(app, monkeypatch, preguntas):
    monkeypatch.setattr(
        identidad, "_llave_del_pase", lambda token, url: LLAVE.public_key()
    )
    app.config["ECOSYSTEM_JWKS_URL"] = "https://ejemplo.invalid/auth/jwks"
    return app.test_client()


def pase(sub, email, rol="admin", org_id=ORG_FEDE, **extra):
    ahora = int(time.time())
    cuerpo = {
        "sub": sub,
        "email": email,
        "fullName": email.split("@")[0],
        "iss": identidad.EMISOR_ECOSYSTEM,
        "iat": ahora,
        "exp": ahora + 1800,
        "app_scopes": ["campeonatos"],
        "role_campeonatos": rol,
    }
    if org_id is not None:
        cuerpo["org_id"] = org_id
    cuerpo.update(extra)
    return jwt.encode(cuerpo, LLAVE, algorithm="RS256")


def canjear(cliente, token):
    return cliente.post("/api/auth/sesion", headers={"Authorization": f"Bearer {token}"})


def fila(email):
    db.session.expire_all()
    return Usuario.query.filter_by(email=email).one()


SUB_A = "aa000000-0000-4000-8000-00000000000a"
SUB_B = "aa000000-0000-4000-8000-00000000000b"


# ══════════════════════════════════════════════════════════════════════════
#  1 · La organización del pase
# ══════════════════════════════════════════════════════════════════════════

class TestLaOrganizacionDelPase:
    def test_se_copia_con_su_nombre(self, cliente):
        assert canjear(cliente, pase(SUB_A, "a@t.org")).status_code == 200
        yo = fila("a@t.org")
        assert yo.org_id == ORG_FEDE
        assert yo.org_nombre == "FEDERACIÓN DEL VALLE"

    def test_viaja_en_el_usuario(self, cliente):
        canjear(cliente, pase(SUB_A, "a@t.org"))
        assert fila("a@t.org").to_dict()["org_nombre"] == "FEDERACIÓN DEL VALLE"

    def test_si_se_cambia_de_organizacion_cambia_con_ella(self, cliente, preguntas):
        canjear(cliente, pase(SUB_A, "a@t.org", org_id=ORG_FEDE))
        canjear(cliente, pase(SUB_A, "a@t.org", org_id=ORG_CLUB))
        yo = fila("a@t.org")
        assert yo.org_id == ORG_CLUB
        assert yo.org_nombre == "DOJANG SUR"

    def test_al_juez_no_se_le_pregunta_nada_pero_se_le_guarda_la_org(self, cliente, preguntas):
        # La regla de siempre (ver test_sso_ecosystem): una petición por cada
        # juez que entra la mañana del campeonato no se paga. El `org_id` sí,
        # porque viene en el pase y no cuesta nada.
        canjear(cliente, pase(SUB_A, "a@t.org", rol="judge"))
        assert preguntas["veces"] == 0
        yo = fila("a@t.org")
        assert (yo.org_id, yo.org_nombre) == (ORG_FEDE, None)

    def test_al_cambiar_de_organizacion_se_olvida_el_nombre_viejo(self, cliente, preguntas):
        canjear(cliente, pase(SUB_A, "a@t.org", rol="judge", org_id=ORG_FEDE))
        juez = fila("a@t.org")
        juez.org_nombre = "UN NOMBRE DE ANTES"
        db.session.commit()
        canjear(cliente, pase(SUB_A, "a@t.org", rol="judge", org_id=ORG_CLUB))
        assert fila("a@t.org").org_nombre is None

    def test_sin_org_en_el_pase_no_se_borra_la_que_habia(self, cliente):
        canjear(cliente, pase(SUB_A, "a@t.org"))
        canjear(cliente, pase(SUB_A, "a@t.org", org_id=None))
        assert fila("a@t.org").org_id == ORG_FEDE

    def test_se_pregunta_una_vez_por_entrada_y_no_en_cada_una(self, cliente, preguntas):
        # Un maestro nuevo necesita su club Y el nombre de la organización: las
        # dos cosas salen de la MISMA pregunta.
        canjear(cliente, pase(SUB_A, "a@t.org", rol="maestro", org_id=ORG_CLUB))
        assert preguntas["veces"] == 1
        # Y la siguiente entrada, con todo ya sabido, no pregunta nada.
        canjear(cliente, pase(SUB_A, "a@t.org", rol="maestro", org_id=ORG_CLUB))
        assert preguntas["veces"] == 1

    def test_si_el_ecosistema_no_contesta_se_entra_igual(self, cliente, preguntas):
        preguntas["nombres"].clear()
        assert canjear(cliente, pase(SUB_A, "a@t.org")).status_code == 200
        yo = fila("a@t.org")
        assert yo.org_id == ORG_FEDE
        assert yo.org_nombre is None


# ══════════════════════════════════════════════════════════════════════════
#  2 · Un solo administrador por organización
# ══════════════════════════════════════════════════════════════════════════

class TestUnSoloAdmin:
    def test_el_primero_entra_de_admin(self, cliente):
        canjear(cliente, pase(SUB_A, "a@t.org"))
        assert fila("a@t.org").rol == "admin"

    def test_el_segundo_de_la_misma_entra_sin_el_papel(self, cliente):
        canjear(cliente, pase(SUB_A, "a@t.org"))
        r = canjear(cliente, pase(SUB_B, "b@t.org"))
        # No se le falla la entrada: entra, trabaja, y alguien lo mira.
        assert r.status_code == 200
        segundo = fila("b@t.org")
        assert segundo.rol == "maestro"
        assert "admin" not in segundo.roles

    def test_conserva_sus_otros_papeles(self, cliente):
        canjear(cliente, pase(SUB_A, "a@t.org"))
        canjear(cliente, pase(SUB_B, "b@t.org", roles_campeonatos=["admin", "judge"]))
        assert fila("b@t.org").roles == ["juez"]

    def test_de_otra_organizacion_si_entra_de_admin(self, cliente):
        canjear(cliente, pase(SUB_A, "a@t.org", org_id=ORG_FEDE))
        canjear(cliente, pase(SUB_B, "b@t.org", org_id=ORG_CLUB))
        assert fila("b@t.org").rol == "admin"

    def test_un_admin_dado_de_baja_no_cuenta(self, cliente):
        canjear(cliente, pase(SUB_A, "a@t.org"))
        primero = fila("a@t.org")
        primero.activo = False
        db.session.commit()
        canjear(cliente, pase(SUB_B, "b@t.org"))
        assert fila("b@t.org").rol == "admin"

    def test_al_super_no_se_le_aplica(self, cliente):
        canjear(cliente, pase(SUB_A, "a@t.org"))
        canjear(cliente, pase(SUB_B, "b@t.org", rol=None, is_super_admin=True))
        assert fila("b@t.org").rol == "admin"

    def test_a_quien_ya_estaba_no_se_le_quita_nada(self, cliente):
        """D3: los admins duplicados de HOY no se tocan — primero el informe."""
        for sub, correo in ((SUB_A, "a@t.org"), (SUB_B, "b@t.org")):
            u = Usuario(email=correo, nombre=correo, rol="admin", eco_sub=sub, activo=True)
            u.set_password("secret123")
            db.session.add(u)
        db.session.commit()
        canjear(cliente, pase(SUB_A, "a@t.org"))
        canjear(cliente, pase(SUB_B, "b@t.org"))
        assert fila("a@t.org").rol == "admin"
        assert fila("b@t.org").rol == "admin"


# ══════════════════════════════════════════════════════════════════════════
#  3 · El campeonato lleva la organización de quien lo crea
# ══════════════════════════════════════════════════════════════════════════

def _token(user):
    from flask_jwt_extended import create_access_token

    return create_access_token(identity=str(user.id))


class TestElCampeonato:
    def test_nace_con_la_de_su_creador(self, cliente):
        canjear(cliente, pase(SUB_A, "a@t.org"))
        admin = fila("a@t.org")
        r = cliente.post(
            "/api/campeonatos",
            json={"nombre": "Copa del Valle", "num_tatamis": 1},
            headers={"Authorization": f"Bearer {_token(admin)}"},
        )
        assert r.status_code == 201, r.get_json()
        assert Campeonato.query.one().org_id == ORG_FEDE

    def test_los_de_antes_la_reciben_cuando_su_creador_entra(self, cliente):
        admin = Usuario(email="a@t.org", nombre="A", rol="admin", activo=True)
        admin.set_password("secret123")
        db.session.add(admin)
        db.session.commit()
        db.session.add(Campeonato(nombre="VIEJO", created_by=admin.id))
        db.session.commit()
        assert Campeonato.query.one().org_id is None

        # Entra desde el portal por primera vez (se enlaza por correo).
        canjear(cliente, pase(SUB_A, "a@t.org"))
        db.session.expire_all()
        assert Campeonato.query.one().org_id == ORG_FEDE

    def test_uno_con_organizacion_no_se_cambia(self, cliente):
        admin = Usuario(email="a@t.org", nombre="A", rol="admin", activo=True,
                        eco_sub=SUB_A, org_id=ORG_FEDE)
        admin.set_password("secret123")
        db.session.add(admin)
        db.session.commit()
        db.session.add(Campeonato(nombre="DE ANTES", created_by=admin.id, org_id=ORG_FEDE))
        db.session.commit()
        # Se cambia de organización: lo que organizó sigue siendo de la de antes.
        canjear(cliente, pase(SUB_A, "a@t.org", org_id=ORG_CLUB))
        db.session.expire_all()
        assert Campeonato.query.one().org_id == ORG_FEDE

    def test_el_arranque_rellena_los_que_puede(self, app):
        from app.organizacion import rellenar_org_de_campeonatos

        con = Usuario(email="a@t.org", nombre="A", rol="admin", activo=True, org_id=ORG_FEDE)
        sin = Usuario(email="b@t.org", nombre="B", rol="admin", activo=True)
        for u in (con, sin):
            u.set_password("secret123")
            db.session.add(u)
        db.session.commit()
        db.session.add_all([
            Campeonato(nombre="UNO", created_by=con.id),
            Campeonato(nombre="DOS", created_by=sin.id),
        ])
        db.session.commit()

        assert rellenar_org_de_campeonatos() == 1
        db.session.commit()
        orgs = {c.nombre: c.org_id for c in Campeonato.query.all()}
        assert orgs == {"UNO": ORG_FEDE, "DOS": None}
        # Idempotente: la segunda pasada no escribe nada.
        assert rellenar_org_de_campeonatos() == 0


# ══════════════════════════════════════════════════════════════════════════
#  4 · El informe de D3
# ══════════════════════════════════════════════════════════════════════════

class TestElInforme:
    def _admins(self):
        filas = [
            Usuario(email="super@t.org", nombre="SUPER", rol="admin", activo=True,
                    es_superadmin=True),
            Usuario(email="a@t.org", nombre="ANA", rol="admin", activo=True,
                    org_id=ORG_FEDE, org_nombre="FEDERACIÓN DEL VALLE"),
            Usuario(email="b@t.org", nombre="BETO", rol="admin", activo=True, org_id=ORG_FEDE),
            Usuario(email="c@t.org", nombre="CARLA", rol="admin", activo=True, org_id=ORG_CLUB),
            Usuario(email="d@t.org", nombre="DANI", rol="admin", activo=True),
            Usuario(email="e@t.org", nombre="EVA", rol="admin", activo=False, org_id=ORG_CLUB),
        ]
        for u in filas:
            u.set_password("secret123")
            db.session.add(u)
        db.session.commit()
        return {u.email: u for u in filas}

    def test_enseña_las_organizaciones_con_mas_de_uno(self, cliente):
        gente = self._admins()
        r = cliente.get(
            "/api/auth/organizaciones/administradores",
            headers={"Authorization": f"Bearer {_token(gente['super@t.org'])}"},
        )
        assert r.status_code == 200
        informe = r.get_json()
        assert len(informe["varios"]) == 1
        grupo = informe["varios"][0]
        assert grupo["org_nombre"] == "FEDERACIÓN DEL VALLE"
        assert sorted(a["email"] for a in grupo["admins"]) == ["a@t.org", "b@t.org"]
        # CARLA sola en su club (la otra está dada de baja).
        assert informe["con_uno"] == 1
        # El super no es admin de ninguna organización: no sale.
        assert [a["email"] for a in informe["sin_organizacion"]] == ["d@t.org"]

    def test_un_admin_normal_no_lo_ve(self, cliente):
        gente = self._admins()
        r = cliente.get(
            "/api/auth/organizaciones/administradores",
            headers={"Authorization": f"Bearer {_token(gente['a@t.org'])}"},
        )
        assert r.status_code == 403
