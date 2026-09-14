"""
Una persona, varios papeles en Campeonatos (F2 de `PLAN-CAMPEONATOS.md`).

Tres cosas, en este orden:

  1. **El modelo.** `roles` es la lista y la verdad; `rol` y `puede_juzgar` los
     escribe su setter. Lo que más importa probar es que **una fila anterior a
     F2 contesta exactamente lo mismo que antes**, sin backfill.
  2. **El pase da papeles** a quien ya estaba, sin quitar ninguno, sin devolver
     los que quitó la consola, y sin dar nunca `admin` (D2 del plan).
  3. **La consola quita**, y lo que quita se recuerda.
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
from app.models.usuario import Usuario, ordenar_papeles  # noqa: E402

DevelopmentConfig.SQLALCHEMY_DATABASE_URI = "sqlite://"

LLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
SUB = "aa000000-0000-4000-8000-0000000000f2"
CORREO = "persona@dinamyt.org"


@pytest.fixture()
def app():
    aplicacion = create_app("development")
    with aplicacion.app_context():
        db.create_all()
        yield aplicacion
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def cliente(app, monkeypatch):
    monkeypatch.setattr(
        identidad, "_llave_del_pase", lambda token, url: LLAVE.public_key()
    )
    # El club se pregunta al ecosistema por la red; aquí no importa y cuesta
    # dos segundos de espera por prueba.
    monkeypatch.setattr(espejo, "club_del_pase", lambda claims, pase: None)
    app.config["ECOSYSTEM_JWKS_URL"] = "https://ejemplo.invalid/auth/jwks"
    return app.test_client()


def pase(rol="maestro", roles=None, **extra):
    ahora = int(time.time())
    cuerpo = {
        "sub": SUB,
        "email": CORREO,
        "fullName": "Persona De Prueba",
        "iss": identidad.EMISOR_ECOSYSTEM,
        "iat": ahora,
        "exp": ahora + 1800,
        "app_scopes": ["campeonatos"],
        "role_campeonatos": rol,
    }
    if roles is not None:
        cuerpo["roles_campeonatos"] = roles
    cuerpo.update(extra)
    return jwt.encode(cuerpo, LLAVE, algorithm="RS256")


def canjear(cliente, token):
    return cliente.post("/api/auth/sesion", headers={"Authorization": f"Bearer {token}"})


def ya_estaba(rol, roles=None, quitados=None, club="DOJANG SUR"):
    """Una fila que ya existía, enlazada con su cuenta del ecosistema."""
    usuario = Usuario(email=CORREO, nombre="PERSONA", rol=rol, eco_sub=SUB, activo=True)
    usuario.set_password("secret123")
    if rol == "maestro":
        usuario.clubes = [club]
    if roles is not None:
        usuario.roles = roles
    if quitados is not None:
        usuario.roles_quitados = quitados
    db.session.add(usuario)
    db.session.commit()
    return usuario


def de_la_base():
    db.session.expire_all()
    return Usuario.query.filter_by(email=CORREO).one()


# ══════════════════════════════════════════════════════════════════════════
#  1 · El modelo
# ══════════════════════════════════════════════════════════════════════════

class TestUnaFilaDeAntesContestaIgual:
    """Sin backfill: `roles` NULL sale de `rol` + `puede_juzgar`."""

    def test_el_juez(self, app):
        assert Usuario(rol="juez").roles == ["juez"]

    def test_el_maestro_que_juzga(self, app):
        assert Usuario(rol="maestro", puede_juzgar=True).roles == ["maestro", "juez"]

    def test_el_maestro_que_no(self, app):
        assert Usuario(rol="maestro", puede_juzgar=False).roles == ["maestro"]

    def test_un_permiso_de_juez_suelto_en_un_admin_no_cuenta(self, app):
        # Siempre fue de maestros; la API lo ponía en falso para los demás.
        assert Usuario(rol="admin", puede_juzgar=True).roles == ["admin"]

    def test_puede_ser_juez_da_lo_mismo_que_antes(self, app):
        antes = lambda u: u.rol == "juez" or (u.rol == "maestro" and bool(u.puede_juzgar))  # noqa: E731
        for rol in ("admin", "maestro", "juez"):
            for juzga in (True, False, None):
                u = Usuario(rol=rol, puede_juzgar=juzga)
                assert u.puede_ser_juez == antes(u), (rol, juzga)


class TestElSetter:
    def test_fija_el_principal_y_el_permiso(self, app):
        u = Usuario(rol="juez")
        u.roles = ["juez", "maestro"]
        assert u.roles == ["maestro", "juez"]
        assert u.rol == "maestro"
        assert u.puede_juzgar is True

    def test_un_juez_a_secas_no_juzga_ADEMAS(self, app):
        # `puede_juzgar` significa «juzga además de su papel principal», que es
        # lo que siempre significó. El juez lo tiene en falso, como hoy.
        u = Usuario(rol="maestro")
        u.roles = ["juez"]
        assert u.rol == "juez"
        assert u.puede_juzgar is False
        assert u.puede_ser_juez is True

    def test_el_administrador_que_juzga(self, app):
        u = Usuario(rol="juez")
        u.roles = ["juez", "admin"]
        assert u.rol == "admin"
        assert u.puede_ser_juez is True

    def test_lo_desconocido_y_lo_repetido_no_entran(self, app):
        assert ordenar_papeles(["maestro", "sensei", "maestro", None, ""]) == ["maestro"]

    def test_sin_ningun_papel_no_hay_fila(self, app):
        u = Usuario(rol="juez")
        with pytest.raises(ValueError):
            u.roles = []

    def test_desde_F3_se_puede_ser_solo_competidor(self, app):
        # Hasta F3 no había pantalla para quien solo compite y el setter lo
        # rechazaba. Ahora la hay (`/mi-panel`).
        u = Usuario(rol="juez")
        u.roles = ["competidor"]
        assert u.rol == "competidor"
        assert u.puede_juzgar is False
        assert u.puede_ser_juez is False

    def test_competir_se_suma_sin_cambiar_nada_mas(self, app):
        u = Usuario(rol="maestro")
        u.roles = ["maestro", "competidor"]
        assert u.rol == "maestro"
        assert u.puede_juzgar is False


class TestSiAlguienEscribeLasColumnasAMano:
    """Un guion o un endpoint que no conoce la lista: mandan las columnas."""

    def test_rol(self, app):
        u = Usuario(rol="juez")
        u.roles = ["maestro", "juez"]
        u.rol = "juez"
        assert u.roles == ["juez"]

    def test_puede_juzgar(self, app):
        u = Usuario(rol="juez")
        u.roles = ["maestro", "juez"]
        u.puede_juzgar = False
        assert u.roles == ["maestro"]


def test_la_consola_recuerda_lo_que_quita_y_olvida_lo_que_devuelve(app):
    u = Usuario(rol="maestro", puede_juzgar=True)
    quitados, dados = u.fijar_papeles_a_mano(["maestro"])
    assert (quitados, dados) == (["juez"], [])
    assert u.roles_quitados == ["juez"]

    quitados, dados = u.fijar_papeles_a_mano(["maestro", "juez"])
    assert (quitados, dados) == ([], ["juez"])
    assert u.roles_quitados == []


def test_to_dict_lleva_los_papeles(app):
    assert Usuario(rol="maestro", puede_juzgar=True).to_dict()["roles"] == [
        "maestro", "juez",
    ]


# ══════════════════════════════════════════════════════════════════════════
#  2 · El pase da papeles
# ══════════════════════════════════════════════════════════════════════════

class TestLaFilaNace:
    def test_con_todos_los_papeles_del_pase(self, cliente):
        res = canjear(cliente, pase(rol="maestro", roles=["maestro", "judge"]))

        assert res.status_code == 200
        assert res.get_json()["user"]["roles"] == ["maestro", "juez"]
        fila = de_la_base()
        assert fila.rol == "maestro"
        assert fila.puede_ser_juez is True

    def test_un_pase_viejo_sin_lista_entra_como_siempre(self, cliente):
        res = canjear(cliente, pase(rol="judge"))

        assert res.status_code == 200
        assert de_la_base().roles == ["juez"]

    def test_el_alumno_nace_como_competidor(self, cliente):
        # F3: competir ya abre Campeonatos — su panel, no la consola.
        res = canjear(cliente, pase(rol="competitor", roles=["competitor"]))

        assert res.status_code == 200
        assert res.get_json()["user"]["rol"] == "competidor"
        assert de_la_base().roles == ["competidor"]

    def test_sin_ningun_papel_de_campeonatos_sigue_sin_crear_fila(self, cliente):
        # `sin_consola` no desaparece con F3: es la respuesta para quien no
        # opera NI compite.
        res = canjear(cliente, pase(rol="guardian", roles=["guardian"]))

        assert res.status_code == 403
        assert res.get_json()["motivo"] == "sin_consola"
        assert Usuario.query.count() == 0

    def test_si_trae_un_papel_que_opera_y_compite_nace_con_los_dos(self, cliente):
        res = canjear(cliente, pase(rol="competitor", roles=["judge", "competitor"]))

        assert res.status_code == 200
        assert de_la_base().roles == ["juez", "competidor"]


class TestAQuienYaEstaba:
    def test_se_le_SUMA_lo_que_el_portal_le_dio(self, cliente):
        # «Lo puse en el portal y allí no cambia nada»: con la regla vieja, el
        # maestro que además juzga seguía sin poder juzgar aquí para siempre.
        ya_estaba("maestro")

        res = canjear(cliente, pase(rol="maestro", roles=["maestro", "judge"]))

        assert res.status_code == 200
        fila = de_la_base()
        assert fila.roles == ["maestro", "juez"]
        assert fila.rol == "maestro"

    def test_no_se_le_quita_lo_que_tiene(self, cliente):
        # El degradado en silencio que la regla vieja evitaba, y sigue evitando.
        ya_estaba("maestro", roles=["maestro", "juez"])

        canjear(cliente, pase(rol="maestro", roles=["maestro"]))

        assert de_la_base().roles == ["maestro", "juez"]

    def test_el_pase_nunca_da_administrador(self, cliente):
        # El mando se pone a mano aquí, y F4 todavía no ha contado cuántos hay.
        ya_estaba("maestro")

        res = canjear(cliente, pase(rol="admin", roles=["admin", "maestro"]))

        assert res.status_code == 200
        fila = de_la_base()
        assert fila.rol == "maestro"
        assert "admin" not in fila.roles

    def test_lo_que_quito_la_consola_no_lo_devuelve_el_pase(self, cliente):
        ya_estaba("maestro", quitados=["juez"])

        canjear(cliente, pase(rol="maestro", roles=["maestro", "judge"]))

        assert de_la_base().roles == ["maestro"]

    def test_competir_se_suma_sin_cambiarle_la_consola(self, cliente):
        ya_estaba("juez")

        res = canjear(cliente, pase(rol="judge", roles=["judge", "competitor"]))

        assert res.get_json()["user"]["rol"] == "juez"
        assert de_la_base().roles == ["juez", "competidor"]

    def test_a_un_desactivado_no_se_le_escribe_nada(self, cliente):
        usuario = ya_estaba("maestro")
        usuario.activo = False
        db.session.commit()

        res = canjear(cliente, pase(rol="maestro", roles=["maestro", "judge"]))

        assert res.status_code == 403
        assert de_la_base().roles == ["maestro"]


# ══════════════════════════════════════════════════════════════════════════
#  3 · La consola quita, y se recuerda
# ══════════════════════════════════════════════════════════════════════════

@pytest.fixture()
def consola(app):
    from flask_jwt_extended import create_access_token

    admin = Usuario(email="admin@test.local", nombre="ADMIN", rol="admin",
                    es_superadmin=True, activo=True)
    admin.set_password("secret123")
    db.session.add(admin)
    db.session.commit()
    token = create_access_token(
        identity=str(admin.id),
        additional_claims={"rol": "admin", "nombre": admin.nombre, "email": admin.email},
    )
    return app.test_client(), {"Authorization": f"Bearer {token}"}


def _crear_maestro_que_juzga(cliente, cabecera):
    res = cliente.post("/api/auth/register", headers=cabecera, json={
        "email": CORREO, "password": "secret123", "nombre": "Maestro Que Juzga",
        "rol": "maestro", "club": "Dojang Sur", "puede_juzgar": True,
    })
    assert res.status_code == 201
    assert res.get_json()["user"]["roles"] == ["maestro", "juez"]
    return res.get_json()["user"]["id"]


def test_quitar_el_permiso_de_juez_lo_recuerda(consola):
    cliente, cabecera = consola
    uid = _crear_maestro_que_juzga(cliente, cabecera)

    res = cliente.put(f"/api/auth/users/{uid}", headers=cabecera, json={"puede_juzgar": False})

    assert res.status_code == 200
    fila = de_la_base()
    assert fila.roles == ["maestro"]
    # Y el pase ya no se lo puede devolver.
    assert fila.roles_quitados == ["juez"]


def test_volver_a_darlo_lo_olvida(consola):
    cliente, cabecera = consola
    uid = _crear_maestro_que_juzga(cliente, cabecera)
    cliente.put(f"/api/auth/users/{uid}", headers=cabecera, json={"puede_juzgar": False})

    cliente.put(f"/api/auth/users/{uid}", headers=cabecera, json={"puede_juzgar": True})

    fila = de_la_base()
    assert fila.roles == ["maestro", "juez"]
    assert fila.roles_quitados == []


def test_editar_el_nombre_no_le_quita_lo_que_la_pantalla_no_ensena(consola):
    # `competidor` lo trajo el pase, y esta pantalla ni siquiera lo enseña: una
    # edición del nombre no puede llevárselo por delante.
    cliente, cabecera = consola
    uid = _crear_maestro_que_juzga(cliente, cabecera)
    fila = de_la_base()
    fila.roles = ["maestro", "juez", "competidor"]
    db.session.commit()

    res = cliente.put(f"/api/auth/users/{uid}", headers=cabecera, json={"nombre": "Otro Nombre"})

    assert res.status_code == 200
    assert de_la_base().roles == ["maestro", "juez", "competidor"]
    assert de_la_base().roles_quitados == []


def test_cambiarle_el_rol_quita_el_anterior_y_lo_recuerda(consola):
    cliente, cabecera = consola
    uid = _crear_maestro_que_juzga(cliente, cabecera)

    res = cliente.put(f"/api/auth/users/{uid}", headers=cabecera, json={"rol": "juez"})

    assert res.status_code == 200
    fila = de_la_base()
    assert fila.roles == ["juez"]
    assert fila.roles_quitados == ["maestro"]


# ══════════════════════════════════════════════════════════════════════════
#  4 · El paquete lleva la lista (F6-b)
# ══════════════════════════════════════════════════════════════════════════

def test_el_paquete_exporta_los_papeles(app):
    from app.api.sincronizacion import VERSION_PAQUETE, _usuario_a_dict

    # 3 desde F2; F3 la subió a 4 (las fichas llevan `eco_sub`). Lo que se
    # prueba aquí es que no baje de la que trajo los papeles.
    assert VERSION_PAQUETE >= 3
    u = Usuario(email="m@x.org", nombre="M", rol="maestro", puede_juzgar=True, activo=True)
    assert _usuario_a_dict(u)["roles"] == ["maestro", "juez"]


class TestLosPapelesDelPaquete:
    def test_una_lista_buena_pasa(self, app):
        from app.api.sincronizacion import _papeles_del_paquete

        assert _papeles_del_paquete(["juez", "maestro"], "maestro") == ["maestro", "juez"]

    def test_un_paquete_viejo_no_trae_lista(self, app):
        from app.api.sincronizacion import _papeles_del_paquete

        assert _papeles_del_paquete(None, "juez") is None

    def test_una_importacion_no_da_administradores(self, app):
        from app.api.sincronizacion import _papeles_del_paquete

        assert _papeles_del_paquete(["admin", "maestro"], "maestro") == ["maestro"]

    def test_el_principal_lo_decide_rol(self, app):
        from app.api.sincronizacion import _papeles_del_paquete

        # Nada por encima de `rol`, y si la lista no lo nombra, se añade.
        assert _papeles_del_paquete(["maestro", "juez"], "juez") == ["juez"]
        assert _papeles_del_paquete(["juez"], "maestro") == ["maestro", "juez"]
