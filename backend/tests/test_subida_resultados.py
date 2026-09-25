"""
La subida automática de resultados (F8 de `PLAN-CAMPEONATOS.md`).

Dos instalaciones de verdad en el mismo proceso —la del EVENTO y la de
INTERNET, cada una con su base— y el cartero hablando con la segunda a través
de su cliente de pruebas, no de un simulacro. Es la única forma de comprobar
lo que importa: que el pase abre sesión allá, que la cookie se lee bien (llega
en DOS `Set-Cookie`), y que lo que sube es exactamente lo que el USB llevaría.

Lo que se defiende:

  1. El admin entra con DINAMYT en el PC del evento y los resultados suben.
  2. Lo subido no se vuelve a subir; lo que cambia, sí.
  3. Sin destino, sin sesión o con un combate en marcha no se sube nada, y se
     dice por qué.
  4. Un fallo de red queda anotado y espera cada vez más; el botón lo fuerza.
  5. El pase vive solo en memoria y se olvida al salir.
"""

import sys
import time
from pathlib import Path
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jwt  # noqa: E402
import pytest  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

from app import cartero, create_app, espejo, identidad  # noqa: E402
from app.config import DevelopmentConfig  # noqa: E402
from app.extensions import db  # noqa: E402

LLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
INTERNET = "https://campeonatos.ejemplo.invalid"
SUB_ADMIN = "aa000000-0000-4000-8000-0000000000ad"


def _pase(email="admin@fede.org", sub=SUB_ADMIN, rol="admin"):
    ahora = int(time.time())
    return jwt.encode({
        "sub": sub, "email": email, "fullName": "Admin Fede",
        "iss": identidad.EMISOR_ECOSYSTEM, "iat": ahora, "exp": ahora + 1800,
        "app_scopes": ["campeonatos"], "role_campeonatos": rol,
    }, LLAVE, algorithm="RS256")


def _app():
    DevelopmentConfig.SQLALCHEMY_DATABASE_URI = "sqlite://"
    aplicacion = create_app("development")
    aplicacion.config["ECOSYSTEM_JWKS_URL"] = "https://ejemplo.invalid/auth/jwks"
    return aplicacion


def _campeonato_con_resultados(nombre="COPA DEL EVENTO"):
    from app.api.llaves import generar_estructura, registrar_resultado, siguiente_partido
    from app.models.campeonato import Campeonato
    from app.models.llave import Llave
    from app.models.tatami import Tatami

    camp = Campeonato(nombre=nombre, activo=True, estado="en_curso")
    db.session.add(camp)
    db.session.flush()
    tatami = Tatami(campeonato_id=camp.id, numero=1)
    db.session.add(tatami)
    db.session.flush()
    est = generar_estructura([{"nombre": "ANA"}, {"nombre": "LUIS"}, {"nombre": "MIA"}])
    while (sig := siguiente_partido(est)) is not None:
        registrar_resultado(est, sig[0], sig[1], 1)
    db.session.add(Llave(campeonato_id=camp.id, tatami_id=tatami.id, tipo="combate",
                         nombre="COMBATE -60KG", estado="terminada", estructura=est))
    db.session.commit()
    return camp


class Mundo:
    pass


@pytest.fixture()
def mundo(monkeypatch):
    monkeypatch.setattr(identidad, "_llave_del_pase", lambda token, url: LLAVE.public_key())
    monkeypatch.setattr(espejo, "club_del_pase", lambda claims, pase: None)
    monkeypatch.setenv("CAMPEONATOS_ONLINE_URL", INTERNET)
    # Sin hilo de fondo: aquí se vacía la cola a mano, con el botón.
    monkeypatch.setattr(cartero, "_arrancar_hilo", lambda app: None)
    cartero.olvidar_pase()

    m = Mundo()
    m.internet = _app()
    m.evento = _app()
    with m.internet.app_context():
        db.create_all()
    m.cliente_internet = m.internet.test_client()

    def transporte(metodo, url, cabeceras, cuerpo=None):
        assert url.startswith(INTERNET)
        m.enviados.append(url[len(INTERNET):])
        r = m.cliente_internet.open(url[len(INTERNET):], method=metodo,
                                    headers=cabeceras, json=cuerpo)
        return r.status_code, list(r.headers.items()), r.get_json() or {}

    m.enviados = []
    monkeypatch.setattr(cartero, "_enviar_http", transporte)

    with m.evento.app_context():
        db.create_all()
        m.camp = _campeonato_con_resultados()
        m.cliente = m.evento.test_client()
        yield m
        db.session.remove()
        db.drop_all()
    cartero.olvidar_pase()


def _entrar_con_dinamyt(m, **extra):
    r = m.cliente.post("/api/auth/sesion", headers={"Authorization": f"Bearer {_pase(**extra)}"})
    assert r.status_code == 200, r.get_json()
    return r


def _estado(m):
    return m.cliente.get("/api/subida/estado").get_json()


def _subir(m):
    return m.cliente.post("/api/subida/intentar", headers=_csrf(m))


def _csrf(m):
    galleta = m.cliente.get_cookie("csrf_access_token")
    return {"X-CSRF-TOKEN": galleta.value} if galleta else {}


# ══════════════════════════════════════════════════════════════════════════
#  1 y 2 · Sube, y no sube dos veces lo mismo
# ══════════════════════════════════════════════════════════════════════════

def test_el_admin_entra_con_dinamyt_y_los_resultados_suben(mundo):
    _entrar_con_dinamyt(mundo)
    antes = _estado(mundo)
    assert [p["nombre"] for p in antes["pendientes"]] == ["COPA DEL EVENTO"]
    assert antes["sesion_viva"] is True

    r = _subir(mundo)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["pendientes"] == []
    assert r.get_json()["subidos"][0]["enviado_por"] == "admin@fede.org"

    # Y allá se ven: con el mismo nombre y los mismos podios que el USB.
    with mundo.internet.app_context():
        publicados = mundo.cliente_internet.get("/api/resultados/campeonatos").get_json()
    assert [p["nombre"] for p in publicados] == ["COPA DEL EVENTO"]
    assert publicados[0]["num_resultados"] >= 1


def test_lo_subido_no_se_sube_otra_vez_y_lo_que_cambia_si(mundo):
    _entrar_con_dinamyt(mundo)
    _subir(mundo)
    enviados = len(mundo.enviados)

    assert _subir(mundo).status_code == 200
    assert len(mundo.enviados) == enviados, "sin cambios no se envía nada"

    mundo.camp.nombre = "COPA DEL EVENTO 2026"
    db.session.commit()
    assert [p["nombre"] for p in _estado(mundo)["pendientes"]] == ["COPA DEL EVENTO 2026"]
    assert _subir(mundo).status_code == 200
    assert _estado(mundo)["pendientes"] == []


# ══════════════════════════════════════════════════════════════════════════
#  3 · Cuándo NO sube, y que se diga
# ══════════════════════════════════════════════════════════════════════════

def test_sin_destino_no_hay_subida_y_se_dice(mundo, monkeypatch):
    _entrar_con_dinamyt(mundo)
    monkeypatch.delenv("CAMPEONATOS_ONLINE_URL")
    r = _subir(mundo)
    assert r.status_code == 409
    assert r.get_json()["motivo"] == "sin_destino"
    assert "CAMPEONATOS_ONLINE_URL" in r.get_json()["error"]


def test_sin_sesion_de_dinamyt_espera_y_lo_dice(mundo):
    # Entra con la contraseña de ESTA instalación, como el día del evento.
    from app.models.usuario import Usuario

    admin = Usuario(email="local@t.org", nombre="LOCAL", rol="admin", activo=True)
    admin.set_password("secret123")
    db.session.add(admin)
    db.session.commit()
    mundo.cliente.post("/api/auth/login", json={"email": "local@t.org", "password": "secret123"})

    assert _estado(mundo)["motivo"] == "sin_sesion"
    r = _subir(mundo)
    assert r.status_code == 409
    assert "DINAMYT" in r.get_json()["error"]
    assert mundo.enviados == []


def test_con_un_combate_en_marcha_no_se_sube(mundo):
    from app.models.llave import Llave

    _entrar_con_dinamyt(mundo)
    db.session.add(Llave(campeonato_id=mundo.camp.id, tipo="combate", nombre="EN VIVO",
                         estado="activa", estructura={"competidores": []}))
    db.session.commit()
    r = _subir(mundo)
    assert r.status_code == 409
    assert r.get_json()["motivo"] == "en_combate"
    assert mundo.enviados == []


def test_a_un_juez_no_se_le_guarda_el_pase(mundo):
    _entrar_con_dinamyt(mundo, email="juez@fede.org",
                        sub="aa000000-0000-4000-8000-00000000000j", rol="judge")
    assert cartero._pase_vivo() == (None, None)


def test_solo_el_admin_ve_la_cola(mundo):
    _entrar_con_dinamyt(mundo, email="juez@fede.org",
                        sub="aa000000-0000-4000-8000-00000000000j", rol="judge")
    assert mundo.cliente.get("/api/subida/estado").status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  4 · Los fallos se anotan y esperan
# ══════════════════════════════════════════════════════════════════════════

def test_un_fallo_de_red_queda_anotado_y_espera(mundo, monkeypatch):
    _entrar_con_dinamyt(mundo)

    def sin_red(*args, **kwargs):
        raise URLError("sin red")

    monkeypatch.setattr(cartero, "_enviar_http", sin_red)
    assert _subir(mundo).status_code == 200
    estado = _estado(mundo)
    assert estado["ultimo_error"] and "sin red" in estado["ultimo_error"]
    assert [p["nombre"] for p in estado["pendientes"]] == ["COPA DEL EVENTO"]

    from app.models.subida import SubidaResultados

    fila = SubidaResultados.query.one()
    assert fila.intentos == 1
    assert fila.proximo_intento_at is not None

    # Sin forzar, respeta la espera: no se intenta otra vez.
    cartero.vaciar(forzar=False)
    assert SubidaResultados.query.one().intentos == 1


# ══════════════════════════════════════════════════════════════════════════
#  5 · El pase solo en memoria, y se olvida al salir
# ══════════════════════════════════════════════════════════════════════════

def test_al_salir_el_pase_se_olvida(mundo):
    _entrar_con_dinamyt(mundo)
    assert cartero._pase_vivo()[0] is not None
    mundo.cliente.post("/api/auth/logout", headers=_csrf(mundo))
    assert cartero._pase_vivo() == (None, None)


def test_un_destino_sin_https_no_recibe_el_pase(mundo, monkeypatch):
    """Lo primero que viaja es el pase de DINAMYT: en claro no sale."""
    _entrar_con_dinamyt(mundo)
    monkeypatch.setenv("CAMPEONATOS_ONLINE_URL", "http://campeonatos.ejemplo.invalid")
    r = _subir(mundo)
    assert r.status_code == 409
    assert r.get_json()["motivo"] == "sin_destino"
    assert mundo.enviados == []

    # Hacia este mismo PC sí (un ensayo en casa, las pruebas).
    monkeypatch.setenv("CAMPEONATOS_ONLINE_URL", "http://127.0.0.1:5000/")
    assert cartero.destino() == "http://127.0.0.1:5000"


# ══════════════════════════════════════════════════════════════════════════
#  6 · Una pasada a la vez
# ══════════════════════════════════════════════════════════════════════════

def test_el_boton_no_se_cruza_con_el_hilo(mundo):
    """Dos pasadas a la vez creaban dos veces la misma fila y una reventaba."""
    _entrar_con_dinamyt(mundo)
    assert cartero._vaciando.acquire(blocking=False)  # el hilo, a medio subir
    try:
        r = _subir(mundo)
    finally:
        cartero._vaciando.release()
    assert r.status_code == 409
    assert r.get_json()["motivo"] == "subiendo"
    assert mundo.enviados == []

    assert _subir(mundo).status_code == 200
    assert _estado(mundo)["pendientes"] == []


# ══════════════════════════════════════════════════════════════════════════
#  7 · El camino normal: vuelve al campeonato de quien lo organiza
# ══════════════════════════════════════════════════════════════════════════

UUID_VIVO = "c0000000000000000000000000000001"


def _campeonato_vivo_en_internet(mundo, dueno_email):
    """El campeonato que se creó en internet y se bajó al PC del evento."""
    from app.models.campeonato import Campeonato
    from app.models.usuario import Usuario

    with mundo.internet.app_context():
        dueno = Usuario.query.filter_by(email=dueno_email).first()
        if dueno is None:
            dueno = Usuario(email=dueno_email, nombre="OTRO", rol="admin", activo=True)
            dueno.set_password("secret123")
            db.session.add(dueno)
            db.session.flush()
        db.session.add(Campeonato(nombre="COPA DEL EVENTO", activo=True, estado="en_curso",
                                  created_by=dueno.id, export_uuid=UUID_VIVO))
        db.session.commit()
    # Aquí, el mismo `export_uuid`: es lo que trajo el paquete.
    mundo.camp.export_uuid = UUID_VIVO
    db.session.commit()


def test_vuelve_al_campeonato_vivo_de_quien_lo_organiza(mundo):
    # El organizador ya existe allá: entró a internet con su cuenta de DINAMYT.
    r = mundo.internet.test_client().post(
        "/api/auth/sesion", headers={"Authorization": f"Bearer {_pase()}"})
    assert r.status_code == 200, r.get_json()
    _campeonato_vivo_en_internet(mundo, "admin@fede.org")

    _entrar_con_dinamyt(mundo)
    r = _subir(mundo)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["pendientes"] == []

    with mundo.internet.app_context():
        lista = mundo.cliente_internet.get("/api/resultados/campeonatos").get_json()
    assert [(c["nombre"], c["publicado"]) for c in lista] == [("COPA DEL EVENTO", True)]


def test_a_un_campeonato_ajeno_no_sube_y_queda_dicho(mundo):
    _campeonato_vivo_en_internet(mundo, "otro@fede.org")

    _entrar_con_dinamyt(mundo)
    assert _subir(mundo).status_code == 200
    estado = _estado(mundo)
    assert [p["nombre"] for p in estado["pendientes"]] == ["COPA DEL EVENTO"]
    assert "otro administrador" in estado["ultimo_error"]
