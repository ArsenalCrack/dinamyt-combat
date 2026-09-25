"""
La vuelta de los resultados: del PC del evento a la instalación de internet.

El camino normal (`PLAN-SINCRONIZACION-LOCAL-ONLINE.md`): el campeonato se
crea e inscribe en internet, se BAJA al PC del evento (el paquete lleva su
`export_uuid`), se compite allí, y los resultados VUELVEN a internet con ese
mismo `export_uuid` (`POST /api/resultados/importar`).

Lo que se defiende aquí:

  1. **Que lo que vuelve se vea.** El campeonato sigue activo en internet —es
     el mismo del que salió— y no tiene combates propios. Si el vivo ganaba
     siempre, los resultados subidos quedaban escondidos detrás de uno con
     cero resultados.
  2. **Que nadie pise lo publicado por otro administrador.** Reimportar
     reemplaza, y eso vale para quien lo publicó, no para cualquiera que tenga
     el archivo.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import create_app  # noqa: E402
from app.config import DevelopmentConfig  # noqa: E402
from app.extensions import db  # noqa: E402

UUID = "e0000000000000000000000000000001"


def _token(user):
    from flask_jwt_extended import create_access_token

    return create_access_token(identity=str(user.id))


@pytest.fixture()
def internet():
    DevelopmentConfig.SQLALCHEMY_DATABASE_URI = "sqlite://"
    app = create_app("development")
    with app.app_context():
        db.create_all()
        from app.models.campeonato import Campeonato
        from app.models.usuario import Usuario

        admin = Usuario(email="a@t.org", nombre="ADMIN", rol="admin", activo=True)
        otro = Usuario(email="b@t.org", nombre="OTRO", rol="admin", activo=True)
        for u in (admin, otro):
            u.set_password("secret123")
            db.session.add(u)
        db.session.commit()
        # El campeonato del que salió el paquete: sigue aquí, activo, y sin
        # un solo combate (se compitió en el PC del evento).
        camp = Campeonato(nombre="COPA", estado="finalizado", activo=True,
                          created_by=admin.id, export_uuid=UUID)
        db.session.add(camp)
        db.session.commit()
        yield app.test_client(), {"admin": _token(admin), "otro": _token(otro)}, camp.id
        db.session.remove()
        db.drop_all()


def _sobre(nombre="COPA"):
    return {
        "formato": "dinamyt-resultados",
        "version": 1,
        "export_uuid": UUID,
        "exportado_at": "2026-10-11T20:00:00+00:00",
        "campeonato": {"nombre": nombre},
        "resultados": [
            {"categoria": "INFANTIL -30", "puesto": 1, "nombre": "ANA GOMEZ", "club": "SUR"},
        ],
        "categorias": ["INFANTIL -30"],
        "tatamis": [1],
    }


def _publicar(cliente, token, sobre=None):
    return cliente.post(
        "/api/resultados/importar", json=sobre or _sobre(),
        headers={"Authorization": f"Bearer {token}"},
    )


def test_lo_que_vuelve_del_evento_se_ve_aunque_el_campeonato_siga_activo(internet):
    cliente, tokens, camp_id = internet
    assert _publicar(cliente, tokens["admin"]).status_code == 200

    selector = cliente.get("/api/resultados/campeonatos").get_json()
    copa = [c for c in selector if c["nombre"] == "COPA"]
    # Una sola entrada —no dos «COPA»— y con los resultados que volvieron.
    assert len(copa) == 1
    assert copa[0]["num_resultados"] == 1

    detalle = cliente.get(f"/api/resultados/campeonato/{copa[0]['id']}").get_json()
    assert [r["nombre"] for r in detalle["resultados"]] == ["ANA GOMEZ"]


def test_el_id_del_campeonato_vivo_tambien_lleva_a_lo_publicado(internet):
    """Un enlace viejo a /resultados/<id numérico> no puede quedarse vacío."""
    cliente, tokens, camp_id = internet
    _publicar(cliente, tokens["admin"])
    detalle = cliente.get(f"/api/resultados/campeonato/{camp_id}").get_json()
    assert [r["nombre"] for r in detalle["resultados"]] == ["ANA GOMEZ"]


def test_otro_admin_no_pisa_lo_publicado(internet):
    cliente, tokens, _ = internet
    _publicar(cliente, tokens["admin"])
    r = _publicar(cliente, tokens["otro"], _sobre(nombre="PISADO"))
    assert r.status_code == 409
    detalle = cliente.get(f"/api/resultados/campeonato/pub:{UUID}").get_json()
    assert detalle["campeonato"]["nombre"] == "COPA"


def test_quien_lo_publico_si_lo_reemplaza(internet):
    cliente, tokens, _ = internet
    _publicar(cliente, tokens["admin"])
    r = _publicar(cliente, tokens["admin"], _sobre(nombre="COPA CORREGIDA"))
    assert r.status_code == 200
    assert r.get_json()["nuevo"] is False


def test_otro_admin_no_publica_sobre_un_campeonato_ajeno(internet):
    """Lo publicado tapa al campeonato vivo sin combates: solo su dueño publica.

    Sin esta puerta, quien tuviera el `export_uuid` —viaja en el paquete que se
    baja al PC del evento— haría pasar sus resultados por los de otro.
    """
    cliente, tokens, camp_id = internet
    r = _publicar(cliente, tokens["otro"], _sobre(nombre="FALSA"))
    assert r.status_code == 409
    assert r.get_json()["motivo"] == "campeonato_de_otro"

    selector = cliente.get("/api/resultados/campeonatos").get_json()
    assert [(c["nombre"], c["publicado"]) for c in selector] == [("COPA", False)]
    detalle = cliente.get(f"/api/resultados/campeonato/{camp_id}").get_json()
    assert detalle["resultados"] == []
