"""
Entrar a Campeonatos desde DINAMYT sin segunda contraseña (C3 + el canje).

Aquí se prueba la puerta que une las dos aplicaciones, y sobre todo **a quién
NO le abre**: desde que la federación puede pagar el plan por sus clubes, todo
alumno de un club afiliado tiene `campeonatos` en su pase. Tener el plan no es
operar un campeonato, y esta consola solo sabe de administrar, inscribir y
puntuar.
"""

import json
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
from app.models.usuario import Usuario  # noqa: E402

DevelopmentConfig.SQLALCHEMY_DATABASE_URI = "sqlite://"

LLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
SUB_MAESTRO = "aa000000-0000-4000-8000-000000000001"
ORG_DEL_PASE = "cc000000-0000-4000-8000-000000000003"


@pytest.fixture()
def cliente(monkeypatch):
    # De dónde sale la llave pública ya se prueba en
    # `test_identidad_ecosystem.py`; aquí lo que importa es qué pasa DESPUÉS
    # de verificar la firma, así que se entrega directa y sin red de por medio.
    monkeypatch.setattr(
        identidad, "_llave_del_pase", lambda token, url: LLAVE.public_key()
    )
    app = create_app("development")
    app.config["ECOSYSTEM_JWKS_URL"] = "https://ejemplo.invalid/auth/jwks"
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


def pase(rol="maestro", scopes=("campeonatos",), sub=SUB_MAESTRO, **extra):
    ahora = int(time.time())
    cuerpo = {
        "sub": sub,
        "email": "maestro@dinamyt.org",
        "fullName": "Maestro Del Club",
        "iss": identidad.EMISOR_ECOSYSTEM,
        "iat": ahora,
        "exp": ahora + 1800,
        "app_scopes": list(scopes),
        "role_campeonatos": rol,
        "org_id": ORG_DEL_PASE,
    }
    cuerpo.update(extra)
    return jwt.encode(cuerpo, LLAVE, algorithm="RS256")


def canjear(cliente, token):
    return cliente.post(
        "/api/auth/sesion", headers={"Authorization": f"Bearer {token}"}
    )


def hay_cookie(respuesta, nombre="dinamyt_session"):
    return any(
        c == "Set-Cookie" and v.startswith(f"{nombre}=") for c, v in respuesta.headers
    )


def test_el_maestro_entra_sin_contrasena_y_nace_su_espejo(cliente):
    res = canjear(cliente, pase())

    assert res.status_code == 200
    assert hay_cookie(res)
    assert res.get_json()["user"]["rol"] == "maestro"

    espejo = Usuario.query.filter_by(email="maestro@dinamyt.org").first()
    assert espejo is not None
    assert espejo.eco_sub == SUB_MAESTRO
    # El espejo no se abre con contraseña: se abre con el pase. La que tiene
    # es una que nadie conoce.
    assert espejo.check_password("") is False


def test_entrar_dos_veces_no_crea_dos_filas(cliente):
    assert canjear(cliente, pase()).status_code == 200
    assert canjear(cliente, pase()).status_code == 200
    assert Usuario.query.filter_by(email="maestro@dinamyt.org").count() == 1


def test_a_quien_ya_estaba_se_le_ENLAZA_y_manda_su_rol_local(cliente):
    # La gente que ya operaba campeonatos antes de la identidad única. Su rol
    # aquí lo puso el administrador y no lo cambia el pase: si el portal dice
    # «juez» y aquí es admin, sigue siendo admin — degradar en silencio al
    # dueño de un campeonato en marcha es lo que hay que evitar.
    previo = Usuario(
        email="maestro@dinamyt.org", nombre="EL DE SIEMPRE", rol="admin", activo=True
    )
    previo.set_password("la-de-antes")
    db.session.add(previo)
    db.session.commit()

    res = canjear(cliente, pase(rol="judge"))

    assert res.status_code == 200
    assert res.get_json()["user"]["rol"] == "admin"
    assert Usuario.query.filter_by(email="maestro@dinamyt.org").count() == 1
    assert Usuario.query.filter_by(email="maestro@dinamyt.org").first().eco_sub == SUB_MAESTRO


def test_un_alumno_con_el_plan_de_su_federacion_no_abre_la_consola(cliente):
    # El caso que trajo todo esto: la federación paga Campeonatos, así que su
    # pase trae el scope. No administra, no inscribe y no puntúa.
    res = canjear(cliente, pase(rol="competitor"))

    assert res.status_code == 403
    assert res.get_json()["motivo"] == "sin_consola"
    assert not hay_cookie(res)
    # Y no deja rastro: doscientos alumnos de una federación no son doscientas
    # filas en la tabla de usuarios de la consola.
    assert Usuario.query.count() == 0


def test_sin_rol_de_campeonatos_tampoco(cliente):
    res = canjear(cliente, pase(rol=None))
    assert res.status_code == 403
    assert res.get_json()["motivo"] == "sin_consola"
    assert Usuario.query.count() == 0


def test_sin_plan_no_entra_aunque_sea_maestro(cliente):
    res = canjear(cliente, pase(scopes=("membresias",)))
    assert res.status_code == 403
    assert res.get_json()["motivo"] == "sin_plan"


def test_un_usuario_desactivado_no_entra_por_la_puerta_nueva(cliente):
    previo = Usuario(
        email="maestro@dinamyt.org", nombre="SUSPENDIDO", rol="maestro", activo=False
    )
    previo.set_password("x")
    db.session.add(previo)
    db.session.commit()

    res = canjear(cliente, pase())

    assert res.status_code == 403
    assert res.get_json()["motivo"] == "desactivado"
    assert not hay_cookie(res)


def test_el_correo_de_otra_cuenta_no_se_pisa(cliente):
    previo = Usuario(
        email="maestro@dinamyt.org", nombre="OTRO", rol="maestro", activo=True,
        eco_sub="bb000000-0000-4000-8000-000000000002",
    )
    previo.set_password("x")
    db.session.add(previo)
    db.session.commit()

    res = canjear(cliente, pase())

    assert res.status_code == 409
    assert res.get_json()["motivo"] == "correo_ocupado"
    assert Usuario.query.first().eco_sub == "bb000000-0000-4000-8000-000000000002"


def test_el_qr_del_juez_sigue_funcionando_igual(cliente):
    # La otra puerta: el token propio de Campeonatos. Es el acceso del día del
    # campeonato y no se toca.
    juez = Usuario(email="juez@test.local", nombre="JUEZ", rol="juez", activo=True)
    juez.set_password("clave-de-juez")
    db.session.add(juez)
    db.session.commit()

    login = cliente.post(
        "/api/auth/login", json={"email": "juez@test.local", "password": "clave-de-juez"}
    )
    assert login.status_code == 200

    res = canjear(cliente, login.get_json()["token"])
    assert res.status_code == 200
    assert res.get_json()["user"]["rol"] == "juez"


def test_en_modo_local_el_pase_del_ecosistema_no_sirve(cliente):
    # El 9 de octubre no hay internet ni ecosistema. Sin la variable, el pase
    # es un token cualquiera: no abre nada, y el login propio sigue en pie.
    cliente.application.config["ECOSYSTEM_JWKS_URL"] = ""

    res = canjear(cliente, pase())

    assert res.status_code in (401, 422)
    assert Usuario.query.count() == 0


def test_un_espejo_ya_enlazado_por_la_reconciliacion_entra(cliente):
    # El caso de producción: el guion del 29 de agosto dejó 12 de 22 usuarios
    # con su `eco_sub` puesto. Esa gente no se «enlaza» al entrar: ya lo está,
    # y tiene que pasar por la primera puerta sin tocar el correo.
    previo = Usuario(
        email="maestro@dinamyt.org", nombre="RECONCILIADO", rol="admin",
        activo=True, eco_sub=SUB_MAESTRO,
    )
    previo.set_password("x")
    db.session.add(previo)
    db.session.commit()

    res = canjear(cliente, pase())

    assert res.status_code == 200
    assert res.get_json()["user"]["rol"] == "admin"
    assert Usuario.query.count() == 1


# ── El club del maestro, preguntado al ecosistema ───────────────────────────


class _RespuestaOrg:
    def __init__(self, datos):
        self._datos = json.dumps(datos).encode("utf-8")

    def read(self):
        return self._datos

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _ecosistema_responde(monkeypatch, datos, registro=None):
    def falso(peticion, timeout=None):
        if registro is not None:
            registro.append(peticion.full_url)
        if isinstance(datos, Exception):
            raise datos
        return _RespuestaOrg(datos)

    monkeypatch.setattr(espejo, "urlopen", falso)


def test_el_maestro_nuevo_estrena_el_club_de_su_pase(cliente, monkeypatch):
    # Sin esto, el maestro entra por SSO y la consola le dice «tu administrador
    # aún no te asignó un club»: no puede inscribir a nadie.
    llamadas = []
    _ecosistema_responde(
        monkeypatch,
        {"name": "Dojang Sur", "delegation": "Cali", "delegationCountry": "Colombia"},
        llamadas,
    )

    assert canjear(cliente, pase()).status_code == 200

    espejo_creado = Usuario.query.filter_by(email="maestro@dinamyt.org").first()
    assert espejo_creado.clubes == [
        {"nombre": "DOJANG SUR", "ciudad": "Cali", "pais": "Colombia"}
    ]
    # Se le pregunta al ecosistema por SU organización, la del pase.
    assert llamadas and llamadas[0].endswith("/organizations/" + ORG_DEL_PASE)


def test_el_club_que_ya_tiene_no_se_pisa(cliente, monkeypatch):
    # Los clubes los edita el administrador desde la consola, y un maestro
    # puede dirigir varios. Rellenar por encima en cada login borraría eso.
    previo = Usuario(
        email="maestro@dinamyt.org", nombre="EL DE SIEMPRE", rol="maestro",
        activo=True,
    )
    previo.set_password("x")
    previo.clubes = [{"nombre": "DOJANG NORTE", "ciudad": "Popayán", "pais": "Colombia"}]
    db.session.add(previo)
    db.session.commit()
    _ecosistema_responde(monkeypatch, {"name": "Dojang Sur"})

    assert canjear(cliente, pase()).status_code == 200

    assert Usuario.query.first().clubes[0]["nombre"] == "DOJANG NORTE"


def test_si_el_ecosistema_no_contesta_se_entra_igual(cliente, monkeypatch):
    # Falla hacia fuera en silencio: un ecosistema lento no puede impedir que
    # un maestro entre. Se entra sin club, como se entraba hasta ayer.
    _ecosistema_responde(monkeypatch, OSError("sin red"))

    res = canjear(cliente, pase())

    assert res.status_code == 200
    assert Usuario.query.filter_by(email="maestro@dinamyt.org").first().clubes == []


def test_al_juez_no_se_le_pregunta_por_ningun_club(cliente, monkeypatch):
    # El juez puntúa donde lo asignen: no inscribe a nadie y su club no pinta
    # nada. Preguntarlo sería una petición al ecosistema por cada juez que
    # entra la mañana del campeonato.
    llamadas = []
    _ecosistema_responde(monkeypatch, {"name": "Dojang Sur"}, llamadas)

    assert canjear(cliente, pase(rol="judge")).status_code == 200
    assert llamadas == []


def test_el_super_admin_entra_sin_club_y_sin_plan(cliente):
    # Quien administra la plataforma no pertenece a ningún club, así que su
    # pase no trae `app_scopes` ni rol de campeonatos. Exigírselos lo dejaba
    # fuera de su propia plataforma — con el mensaje «tu club no tiene
    # Campeonatos en su plan», que además no significa nada para él.
    res = canjear(cliente, pase(rol=None, scopes=(), is_super_admin=True))

    assert res.status_code == 200, res.get_json()
    creado = Usuario.query.filter_by(email="maestro@dinamyt.org").first()
    assert creado.rol == "admin"
    # Pero NO se le concede el mando de esta app: eso se da a mano, mirando.
    assert bool(creado.es_superadmin) is False
