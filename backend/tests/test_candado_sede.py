"""
El candado de sede (`app/sede.py`, decisión 8 del plan maestro).

Mientras el campeonato corre en el PC del evento, la instalación que lo cedió
es de SOLO LECTURA para él: dos escritores es exactamente lo que no se puede
arreglar después. Lo que se defiende:

  1. **Cedido, ninguna ruta que escribe sobre el campeonato escribe** (423 con
     su frase), y tampoco se puntúa por el socket — ni el superadmin.
  2. **Mirar sigue abierto**, y también lo que no es del campeonato (la ficha
     de un competidor es del workspace) y el camino de vuelta de los
     resultados.
  3. **Ceder y recuperar son gestos del admin**: el maestro no, y bajarse el
     paquete «para el evento» cede en el mismo gesto; una copia de prueba no.
  4. **Un paquete no pisa un campeonato cedido.**
  5. **Recuperado, todo vuelve a escribirse.**
"""

import io
import json
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

    return create_access_token(identity=str(user.id))


class Mundo:
    pass


@pytest.fixture()
def mundo():
    DevelopmentConfig.SQLALCHEMY_DATABASE_URI = "sqlite://"
    app = create_app("development")
    with app.app_context():
        db.create_all()
        from app.models.asignacion import AsignacionJuez
        from app.models.campeonato import Campeonato
        from app.models.competidor import Competidor, Inscripcion
        from app.models.invitacion import InvitacionClub
        from app.models.llave import Llave
        from app.models.tatami import Tatami
        from app.models.usuario import Usuario

        def usuario(email, rol, **extra):
            u = Usuario(email=email, nombre=email.split("@")[0].upper(), rol=rol,
                        activo=True, **extra)
            u.set_password("secret123")
            db.session.add(u)
            db.session.commit()
            return u

        m = Mundo()
        m.admin = usuario("admin@fede.org", "admin")
        m.maestro = usuario("maestro@t.org", "maestro", creado_por_id=m.admin.id)
        m.juez = usuario("juez@t.org", "juez", creado_por_id=m.admin.id)
        m.super = usuario("super@dinamyt.org", "admin", es_superadmin=True)

        m.camp = Campeonato(nombre="COPA", estado="preparacion", activo=True,
                            created_by=m.admin.id)
        db.session.add(m.camp)
        db.session.commit()
        m.tatami = Tatami(numero=1, campeonato_id=m.camp.id)
        m.comp = Competidor(nombre_completo="ANA PÉREZ", created_by=m.admin.id)
        db.session.add_all([m.tatami, m.comp])
        db.session.commit()
        m.ins = Inscripcion(campeonato_id=m.camp.id, competidor_id=m.comp.id,
                            created_by=m.maestro.id)
        m.llave = Llave(nombre="INFANTIL", campeonato_id=m.camp.id,
                        estructura={"rondas": []})
        m.inv = InvitacionClub(campeonato_id=m.camp.id, club_nombre="CLUB UNO")
        m.asig = AsignacionJuez(tatami_id=m.tatami.id, usuario_id=m.juez.id,
                                rol_tatami="arbitro")
        db.session.add_all([m.ins, m.llave, m.inv, m.asig])
        db.session.commit()

        m.app = app
        m.cliente = app.test_client()
        m.tokens = {n: _token(getattr(m, n)) for n in ("admin", "maestro", "juez", "super")}
        yield m
        db.session.remove()
        db.drop_all()


def _h(m, quien="admin"):
    return {"Authorization": f"Bearer {m.tokens[quien]}"}


def _ceder(m, quien="admin"):
    return m.cliente.post(f"/api/campeonatos/{m.camp.id}/sede", json={"sede": "local"},
                          headers=_h(m, quien))


def _escrituras(m):
    """Todas las rutas que escriben sobre el campeonato: (método, ruta, cuerpo)."""
    c, t, ll, i = m.camp.id, m.tatami.id, m.llave.id, m.ins.id
    return [
        ("put", f"/api/campeonatos/{c}", {"nombre": "COPA 2"}),
        ("put", f"/api/campeonatos/{c}/tatamis", {"num_tatamis": 2}),
        ("delete", f"/api/campeonatos/{c}", None),
        ("put", f"/api/campeonatos/{c}/config-categorias", {}),
        ("post", f"/api/campeonatos/{c}/generar-llaves", {}),
        ("post", f"/api/campeonatos/{c}/clubes", {"nombre": "CLUB DOS"}),
        ("put", f"/api/campeonatos/{c}/clubes/solo-invitados", {"solo_invitados": True}),
        ("delete", f"/api/campeonatos/{c}/clubes/{m.inv.id}", None),
        ("post", f"/api/tatamis/{t}/asignar", {"usuario_id": m.juez.id}),
        ("delete", f"/api/tatamis/{t}/desasignar/{m.juez.id}", None),
        ("post", f"/api/tatamis/{t}/acceso-qr/{m.juez.id}", {}),
        ("post", "/api/llaves", {"campeonato_id": c, "nombre": "X", "competidores": []}),
        ("put", f"/api/llaves/{ll}", {"nombre": "Y"}),
        ("put", f"/api/llaves/{ll}/partido", {}),
        ("delete", f"/api/llaves/{ll}", None),
        ("post", "/api/llaves/combinar", {"llave_ids": [ll, ll]}),
        ("post", "/api/llaves/mover-competidor",
         {"origen_id": ll, "destino_id": ll + 1, "competidor_id": 1}),
        ("post", f"/api/inscripciones/campeonato/{c}", {"competidor_id": m.comp.id}),
        ("put", f"/api/inscripciones/{i}", {"peso": 30}),
        ("patch", f"/api/inscripciones/{i}/estado", {"estado": "rechazada"}),
        ("delete", f"/api/inscripciones/{i}", None),
    ]


# ── 1 · Cedido, nada escribe ─────────────────────────────────────────────────

def test_ceder_deja_el_campeonato_en_solo_lectura(mundo):
    m = mundo
    r = _ceder(m)
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["campeonato"]["sede"] == "local"
    assert r.get_json()["campeonato"]["sede_local_por"] == "admin@fede.org"

    for metodo, ruta, cuerpo in _escrituras(m):
        resp = getattr(m.cliente, metodo)(ruta, json=cuerpo, headers=_h(m))
        assert resp.status_code == 423, f"{metodo.upper()} {ruta} → {resp.status_code}"
        assert "PC del evento" in resp.get_json()["error"]


def test_el_maestro_tampoco_inscribe_en_un_campeonato_cedido(mundo):
    m = mundo
    _ceder(m)
    r = m.cliente.post(f"/api/inscripciones/maestro/campeonato/{m.camp.id}",
                       json={"competidor_id": m.comp.id}, headers=_h(m, "maestro"))
    assert r.status_code == 423
    r = m.cliente.put(f"/api/inscripciones/maestro/{m.ins.id}", json={"peso": 31},
                      headers=_h(m, "maestro"))
    assert r.status_code == 423


def test_cedido_no_se_puntua_ni_siendo_superadmin(mundo):
    m = mundo
    from app.sockets.combate_ns import SEDE_CEDIDA, _motivo_para_no_puntuar

    _ceder(m)
    for quien in ("admin", "juez", "super"):
        assert _motivo_para_no_puntuar(m.tokens[quien], m.tatami.id, "arbitro") == SEDE_CEDIDA


# ── 2 · Lo que sigue abierto ─────────────────────────────────────────────────

def test_mirar_sigue_abierto(mundo):
    m = mundo
    _ceder(m)
    r = m.cliente.get(f"/api/campeonatos/{m.camp.id}", headers=_h(m))
    assert r.status_code == 200
    assert r.get_json()["sede"] == "local"


def test_la_ficha_del_competidor_no_es_del_campeonato(mundo):
    m = mundo
    _ceder(m)
    r = m.cliente.put(f"/api/competidores/{m.comp.id}", json={"nombre_completo": "ANA PÉREZ GÓMEZ"},
                      headers=_h(m))
    assert r.status_code != 423


def test_la_subida_de_resultados_no_pasa_por_el_candado(mundo):
    """Es justo el camino de vuelta: el PC del evento sube con el candado puesto."""
    m = mundo
    _ceder(m)
    r = m.cliente.post("/api/resultados/importar", json={}, headers=_h(m))
    assert r.status_code != 423


# ── 3 · Quién cede, y cómo ───────────────────────────────────────────────────

def test_el_maestro_no_cambia_la_sede(mundo):
    m = mundo
    assert _ceder(m, "maestro").status_code == 403


def test_una_sede_que_no_existe_se_rechaza(mundo):
    m = mundo
    r = m.cliente.post(f"/api/campeonatos/{m.camp.id}/sede", json={"sede": "marte"},
                       headers=_h(m))
    assert r.status_code == 400


def test_bajarse_el_paquete_para_el_evento_cede_y_una_copia_no(mundo):
    m = mundo
    ruta = f"/api/sincronizacion/campeonato/{m.camp.id}/exportar"
    assert m.cliente.get(ruta, headers=_h(m)).status_code == 200
    with m.app.app_context():
        from app.models.campeonato import Campeonato
        assert db.session.get(Campeonato, m.camp.id).sede_local_desde is None

    r = m.cliente.get(ruta + "?para_el_evento=1", headers=_h(m))
    assert r.status_code == 200
    # El paquete NO lleva la marca: la copia del evento nace sin candado.
    assert "sede_local_desde" not in json.dumps(r.get_json()["campeonato"])
    with m.app.app_context():
        from app.models.campeonato import Campeonato
        assert db.session.get(Campeonato, m.camp.id).sede_local_desde is not None


def test_ceder_dos_veces_conserva_la_fecha_de_la_primera(mundo):
    m = mundo
    primera = _ceder(m).get_json()["campeonato"]["sede_local_desde"]
    segunda = _ceder(m).get_json()["campeonato"]["sede_local_desde"]
    assert primera == segunda


# ── 4 · Un paquete no pisa un campeonato cedido ──────────────────────────────

def test_importar_encima_de_un_campeonato_cedido_se_niega(mundo):
    m = mundo
    paquete = m.cliente.get(f"/api/sincronizacion/campeonato/{m.camp.id}/exportar",
                            headers=_h(m)).get_json()
    _ceder(m)
    datos = {"file": (io.BytesIO(json.dumps(paquete).encode()), "paquete.json")}
    r = m.cliente.post("/api/sincronizacion/importar", data=datos, headers=_h(m),
                       content_type="multipart/form-data")
    assert r.status_code == 423, r.get_json()


# ── 5 · Recuperado, todo vuelve ──────────────────────────────────────────────

def test_devolverlo_a_la_nube_vuelve_a_dejar_escribir(mundo):
    m = mundo
    _ceder(m)
    r = m.cliente.post(f"/api/campeonatos/{m.camp.id}/sede", json={"sede": "nube"},
                       headers=_h(m))
    assert r.status_code == 200
    assert r.get_json()["campeonato"]["sede"] == "nube"
    r = m.cliente.put(f"/api/campeonatos/{m.camp.id}/clubes/solo-invitados",
                      json={"solo_invitados": True}, headers=_h(m))
    assert r.status_code == 200
    from app.sockets.combate_ns import _motivo_para_no_puntuar
    assert _motivo_para_no_puntuar(m.tokens["admin"], m.tatami.id, "arbitro") is None
