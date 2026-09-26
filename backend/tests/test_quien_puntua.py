"""
Quién puede puntuar en un tatami (revisión de seguridad del 25 sep 2026).

Hasta hoy el socket `/combate` aceptaba a cualquiera en cualquier papel: sin
token se entraba como Juez Central (y se echaba al de verdad), y el juez de un
`punto_juez` salía del mensaje — hasta la pantalla pública podía puntuar a
nombre del Juez 1. Lo que se defiende ahora:

  1. La pantalla entra sin nada, y solo mira.
  2. Para puntuar: token de esta instalación de alguien activo que sea
     superadmin, admin dueño del campeonato, o juez asignado a ESE tatami con
     ESE papel.
  3. El juez de un punto es el de la conexión.
  4. Nadie sin permiso puede echar al juez de verdad.
  5. `TATAMI_SIN_IDENTIDAD=1` devuelve lo de antes (la salida de emergencia
     del PC del evento).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import create_app  # noqa: E402
from app.config import DevelopmentConfig  # noqa: E402
from app.extensions import db, socketio  # noqa: E402

DevelopmentConfig.SQLALCHEMY_DATABASE_URI = "sqlite://"


class Mundo:
    pass


@pytest.fixture()
def mundo(tmp_path, monkeypatch):
    monkeypatch.delenv("TATAMI_SIN_IDENTIDAD", raising=False)
    app = create_app("development")
    from app.sockets import combate_ns

    combate_ns._SNAPSHOT_PATH = tmp_path / "tatamis.json"
    combate_ns._snapshots_cargados = True
    combate_ns.tatami_states.clear()

    with app.app_context():
        db.create_all()
        from flask_jwt_extended import create_access_token
        from app.models.asignacion import AsignacionJuez
        from app.models.campeonato import Campeonato
        from app.models.tatami import Tatami
        from app.models.usuario import Usuario

        def usuario(email, rol, **extra):
            u = Usuario(email=email, nombre=email.split("@")[0].upper(), rol=rol,
                        activo=True, **extra)
            u.set_password("x")
            db.session.add(u)
            db.session.commit()
            return u

        m = Mundo()
        m.app = app
        m.dueno = usuario("dueno@t.org", "admin")
        m.otro_admin = usuario("otro@t.org", "admin")
        m.juez = usuario("juez@t.org", "juez", creado_por_id=m.dueno.id)
        m.sin_asignar = usuario("libre@t.org", "juez", creado_por_id=m.dueno.id)
        m.apagado = usuario("apagado@t.org", "juez", creado_por_id=m.dueno.id)
        camp = Campeonato(nombre="COPA", activo=True, created_by=m.dueno.id)
        db.session.add(camp)
        db.session.flush()
        tatami = Tatami(campeonato_id=camp.id, numero=1)
        db.session.add(tatami)
        db.session.flush()
        m.tatami_id = tatami.id
        db.session.add_all([
            AsignacionJuez(tatami_id=tatami.id, usuario_id=m.juez.id, rol_tatami="j1"),
            AsignacionJuez(tatami_id=tatami.id, usuario_id=m.apagado.id, rol_tatami="j2"),
        ])
        m.apagado.activo = False
        db.session.commit()
        m.token = {
            nombre: create_access_token(identity=str(getattr(m, nombre).id))
            for nombre in ("dueno", "otro_admin", "juez", "sin_asignar", "apagado")
        }
        yield m
        db.session.remove()
        db.drop_all()


def _conectar(m, rol, quien=None, token=None):
    kwargs = {}
    if quien or token:
        kwargs["auth"] = {"token": token or m.token[quien]}
    return socketio.test_client(
        m.app, namespace="/combate", query_string=f"tatami_id={m.tatami_id}&rol={rol}",
        **kwargs,
    )


def _emitir(cliente, accion, n=[0], **datos):
    n[0] += 1
    cliente.emit("evento", {"evId": f"q{n[0]}", "evento": {"accion": accion, **datos}},
                 namespace="/combate")


def _estado(cliente):
    estados = [r["args"][0]["datos"] for r in cliente.get_received("/combate")
               if r["name"] in ("estado", "estado_confirmado") and r["args"]]
    return estados[-1] if estados else None


def _rechazos(cliente):
    return [r["args"][0]["message"] for r in cliente.get_received("/combate")
            if r["name"] == "accion_rechazada" and r["args"]]


# ── 1 · La pantalla ─────────────────────────────────────────────────────────

def test_la_pantalla_entra_sin_nada(mundo):
    assert _conectar(mundo, "pantalla").is_connected("/combate")


def test_la_pantalla_no_manda_nada(mundo):
    arbitro = _conectar(mundo, "arbitro", "dueno")
    _emitir(arbitro, "activar_tatami")
    _emitir(arbitro, "nombres", nombreHong="ANA", nombreChung="LUIS")
    pantalla = _conectar(mundo, "pantalla")
    _emitir(pantalla, "nombres", nombreHong="FALSO", nombreChung="FALSO")
    _emitir(pantalla, "desactivar_tatami")
    _emitir(arbitro, "nombres", nombreHong="ANA", nombreChung="LUIS B")
    estado = _estado(arbitro)
    assert (estado["nombreHong"], estado["nombreChung"]) == ("ANA", "LUIS B")
    assert estado.get("_tatami_activo") is not False


# ── 2 · Quién puede tomar un papel que puntúa ───────────────────────────────

@pytest.mark.parametrize("rol", ["arbitro", "j1", "j2", "j3", "j4"])
def test_sin_token_nadie_puntua(mundo, rol):
    assert not _conectar(mundo, rol).is_connected("/combate")


@pytest.mark.parametrize("quien, rol, entra", [
    ("dueno", "arbitro", True),        # el admin dueño del campeonato
    ("dueno", "j3", True),
    ("otro_admin", "arbitro", False),  # un admin de otro workspace
    ("juez", "j1", True),              # el juez asignado, en SU papel
    ("juez", "arbitro", False),        # …pero no en otro
    ("juez", "j2", False),
    ("sin_asignar", "j1", False),      # un juez que no es de este tatami
    ("apagado", "j2", False),          # asignado, pero desactivado
])
def test_quien_entra_a_que_papel(mundo, quien, rol, entra):
    assert _conectar(mundo, rol, quien).is_connected("/combate") is entra


def test_un_token_falso_no_entra(mundo):
    assert not _conectar(mundo, "arbitro", token="esto.no.es-un-token").is_connected("/combate")


# ── 3 · El juez de un punto es el de la conexión ────────────────────────────

def test_no_se_puntua_a_nombre_de_otro_juez(mundo):
    arbitro = _conectar(mundo, "arbitro", "dueno")
    _emitir(arbitro, "activar_tatami")
    _emitir(arbitro, "nombres", nombreHong="ANA", nombreChung="LUIS")
    j1 = _conectar(mundo, "j1", "juez")
    antes = len(_estado(arbitro)["historial"])

    _emitir(j1, "punto_juez", juez="j2", color="hong", pts=2, nombre="x")
    assert _rechazos(j1) == ["Solo puedes puntuar como Juez 1."]

    _emitir(j1, "punto_juez", juez="j1", color="hong", pts=2, nombre="x")
    assert len(_estado(arbitro)["historial"]) > antes


# ── 4 · Nadie sin permiso echa al juez de verdad ────────────────────────────

def test_sin_permiso_no_hay_takeover(mundo):
    j1 = _conectar(mundo, "j1", "juez")
    intruso = _conectar(mundo, "j1", "sin_asignar")
    assert not intruso.is_connected("/combate")
    assert j1.is_connected("/combate")
    assert not any(r["name"] == "sesion_reemplazada" for r in j1.get_received("/combate"))


# ── 5 · La salida de emergencia ─────────────────────────────────────────────

def test_la_salida_de_emergencia_devuelve_lo_de_antes(mundo, monkeypatch):
    monkeypatch.setenv("TATAMI_SIN_IDENTIDAD", "1")
    assert _conectar(mundo, "arbitro").is_connected("/combate")
