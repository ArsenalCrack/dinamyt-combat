"""
La cuenta se borró en DINAMYT: lo suyo en Campeonatos también.

Lo que se prueba, en orden:

  1. La cuenta se vacía y queda dada de baja; sus accesos a los tatamis (con
     la IP) y sus asignaciones de juez se borran.
  2. La ficha que compitió se queda con su nombre y su club —los resultados
     oficiales lo llevan—, sin documento, nacimiento ni peso; su inscripción a
     un campeonato que sigue en preparación se borra.
  3. La ficha que nunca compitió se borra entera: también la que solo tuvo
     inscripciones que nunca se aceptaron.
  4. Una ficha con su documento que NO está ligada a la cuenta no se toca: es
     del organizador que la cargó.
  5. A nadie más se le toca nada, y una segunda vez no hace nada.
  5. Sin el secreto, la puerta está cerrada; sin la variable, la ruta no existe.
"""

import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import create_app  # noqa: E402
from app.config import DevelopmentConfig  # noqa: E402
from app.extensions import db  # noqa: E402

DevelopmentConfig.SQLALCHEMY_DATABASE_URI = "sqlite://"

SECRETO = "secreto-del-espejo-para-las-pruebas"
SUB_ANA = "aa000000-0000-4000-8000-0000000000a1"


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("ECOSYSTEM_SYNC_SECRET", SECRETO)
    aplicacion = create_app("development")
    with aplicacion.app_context():
        db.create_all()
        yield aplicacion
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def mundo(app):
    from app.models.asignacion import AccesoTatami, AsignacionJuez
    from app.models.campeonato import Campeonato
    from app.models.competidor import Competidor, Inscripcion
    from app.models.tatami import Tatami
    from app.models.usuario import Usuario

    admin = Usuario(email="admin@t.local", nombre="ADMIN", rol="admin", activo=True)
    # La ficha sin enlazar vive en el workspace de OTRO administrador: en el
    # mismo, el documento no se puede repetir.
    otro_admin = Usuario(email="otro@t.local", nombre="OTRO", rol="admin", activo=True)
    ana = Usuario(email="ana@dinamyt.org", nombre="ANA GÓMEZ", rol="competidor",
                  activo=True, eco_sub=SUB_ANA, club="DOJANG SUR")
    for u in (admin, otro_admin, ana):
        u.set_password("secret123")
        db.session.add(u)
    db.session.commit()

    pasado = Campeonato(nombre="COPA 2025", activo=True, estado="finalizado",
                        fecha_inicio=date(2025, 5, 1), created_by=admin.id)
    proximo = Campeonato(nombre="COPA 2027", activo=True, estado="preparacion",
                         fecha_inicio=date(2027, 5, 1), created_by=admin.id)
    db.session.add_all([pasado, proximo])
    db.session.flush()

    compitio = Competidor(nombre_completo="ANA GÓMEZ", documento="1001",
                          fecha_nacimiento=date(2010, 4, 2), peso=52.5, club="DOJANG SUR",
                          activo=True, created_by=admin.id, eco_sub=SUB_ANA)
    sin_enlazar = Competidor(nombre_completo="ANA GOMEZ", documento="1001",
                             fecha_nacimiento=date(2010, 4, 2), club="DOJANG SUR",
                             activo=True, created_by=otro_admin.id)
    # Ligada a la cuenta, pero solo con una inscripción rechazada en un
    # campeonato que ya acabó: nunca compitió.
    rechazada = Competidor(nombre_completo="ANA GÓMEZ", documento="1003",
                           fecha_nacimiento=date(2010, 4, 2), club="DOJANG SUR",
                           activo=True, created_by=otro_admin.id, eco_sub=SUB_ANA)
    otra = Competidor(nombre_completo="LUZ MARINA", documento="2002",
                      fecha_nacimiento=date(2011, 7, 9), club="DOJANG SUR",
                      activo=True, created_by=admin.id)
    db.session.add_all([compitio, sin_enlazar, rechazada, otra])
    db.session.flush()

    db.session.add_all([
        Inscripcion(campeonato_id=pasado.id, competidor_id=compitio.id, estado="aceptada"),
        Inscripcion(campeonato_id=proximo.id, competidor_id=compitio.id, estado="aceptada"),
        Inscripcion(campeonato_id=proximo.id, competidor_id=sin_enlazar.id, estado="pendiente"),
        Inscripcion(campeonato_id=proximo.id, competidor_id=otra.id, estado="aceptada"),
        Inscripcion(campeonato_id=pasado.id, competidor_id=rechazada.id, estado="rechazada"),
    ])
    tatami = Tatami(numero=1, campeonato_id=pasado.id)
    db.session.add(tatami)
    db.session.flush()
    db.session.add(AccesoTatami(tatami_id=tatami.id, usuario_id=ana.id, ip_address="10.0.0.9"))
    db.session.add(AsignacionJuez(tatami_id=tatami.id, usuario_id=ana.id, rol_tatami="j1",
                                  nombre_display="ANA GÓMEZ", asignado_por_id=admin.id))
    db.session.commit()

    return SimpleNamespace(
        cliente=app.test_client(),
        ana_id=ana.id, compitio_id=compitio.id, sin_enlazar_id=sin_enlazar.id,
        rechazada_id=rechazada.id, otra_id=otra.id, pasado_id=pasado.id,
        proximo_id=proximo.id,
    )


def _suprimir(m, cuerpo=None, secreto=SECRETO):
    cabeceras = {} if secreto is None else {"x-dinamyt-sync": secreto}
    return m.cliente.post("/api/sync/supresion",
                          json=cuerpo or {"ecoSub": SUB_ANA},
                          headers=cabeceras)


def test_vacia_la_cuenta_y_borra_sus_accesos(mundo):
    from app.models.asignacion import AccesoTatami, AsignacionJuez
    from app.models.usuario import Usuario

    res = _suprimir(mundo)
    assert res.status_code == 200, res.get_json()
    assert res.get_json() == {"usuarios": 1, "competidoresBorrados": 1, "competidoresConservados": 1}

    ana = db.session.get(Usuario, mundo.ana_id)
    assert ana.nombre == "PERSONA ELIMINADA"
    assert ana.email == f"eliminado-{mundo.ana_id}@eliminado.invalid"
    assert ana.eco_sub is None
    assert ana.club is None
    assert ana.activo is False
    assert ana.eliminado_at is not None
    assert not ana.check_password("secret123")
    assert ana.clubes == []
    assert AccesoTatami.query.filter_by(usuario_id=mundo.ana_id).count() == 0
    # Sin esto seguía asignada a su tatami como «PERSONA ELIMINADA».
    assert AsignacionJuez.query.filter_by(usuario_id=mundo.ana_id).count() == 0


def test_la_ficha_que_compitio_se_queda_con_su_nombre_y_sin_lo_demas(mundo):
    from app.models.competidor import Competidor, Inscripcion

    _suprimir(mundo)
    ficha = db.session.get(Competidor, mundo.compitio_id)
    assert ficha.nombre_completo == "ANA GÓMEZ"
    assert ficha.club == "DOJANG SUR"
    assert ficha.documento is None
    assert ficha.fecha_nacimiento is None
    assert ficha.peso is None
    assert ficha.eco_sub is None
    quedan = {i.campeonato_id for i in Inscripcion.query.filter_by(competidor_id=ficha.id)}
    assert quedan == {mundo.pasado_id}


def test_la_ficha_que_nunca_compitio_se_borra_aunque_el_campeonato_acabara(mundo):
    from app.models.competidor import Competidor, Inscripcion

    _suprimir(mundo)
    assert db.session.get(Competidor, mundo.rechazada_id) is None
    assert Inscripcion.query.filter_by(competidor_id=mundo.rechazada_id).count() == 0


def test_la_ficha_no_ligada_a_la_cuenta_no_se_toca_aunque_traiga_su_documento(mundo):
    from app.models.competidor import Competidor, Inscripcion

    res = _suprimir(mundo, cuerpo={"ecoSub": SUB_ANA, "documento": "1001"})
    assert res.status_code == 200
    ficha = db.session.get(Competidor, mundo.sin_enlazar_id)
    assert ficha is not None
    assert ficha.documento == "1001"
    assert Inscripcion.query.filter_by(competidor_id=mundo.sin_enlazar_id).count() == 1


def test_a_nadie_mas_se_le_toca_nada_y_dos_veces_no_hace_nada(mundo):
    from app.models.competidor import Competidor, Inscripcion

    _suprimir(mundo)
    otra = db.session.get(Competidor, mundo.otra_id)
    assert otra.documento == "2002"
    assert Inscripcion.query.filter_by(competidor_id=mundo.otra_id).count() == 1

    segunda = _suprimir(mundo)
    assert segunda.get_json() == {"usuarios": 0, "competidoresBorrados": 0, "competidoresConservados": 0}


def test_sin_el_secreto_la_puerta_esta_cerrada(mundo):
    from app.models.usuario import Usuario

    assert _suprimir(mundo, secreto=None).status_code == 401
    assert _suprimir(mundo, secreto="otro").status_code == 401
    assert db.session.get(Usuario, mundo.ana_id).nombre == "ANA GÓMEZ"


def test_pide_un_ecosub_que_sea_un_id(mundo):
    assert _suprimir(mundo, cuerpo={"ecoSub": "no"}).status_code == 422


def test_sin_la_variable_la_ruta_no_existe(mundo, monkeypatch):
    monkeypatch.delenv("ECOSYSTEM_SYNC_SECRET")
    assert _suprimir(mundo).status_code == 404
