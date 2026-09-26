"""
Los resultados saben de quién son (F3 de `PLAN-CAMPEONATOS.md`, parte 2).

Hasta hoy ningún resultado apuntaba a una ficha: la llave guardaba a cada
competidor como `{id: posición, nombre, club}`, y «mis resultados» solo se podía
sacar comparando texto. La decisión fue enlazar DESDE HOY: las llaves que se
generan llevan el uid de la ficha, y lo anterior se busca por nombre (marcado
«sin confirmar»).

Lo que se prueba, en orden:
  1. La generación automática deja el enlace en cada competidor y en el cuadro.
  2. Combinar, mover y editar —que re-sortean— NO lo pierden.
  3. Una llave hecha a mano sigue sin enlace (no hay ficha que enlazar).
  4. Lo PÚBLICO no enseña el uid.
  5. En figuras, el enlace entra por el servidor y nunca por el cliente.
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import create_app  # noqa: E402
from app.config import DevelopmentConfig  # noqa: E402
from app.extensions import db  # noqa: E402

DevelopmentConfig.SQLALCHEMY_DATABASE_URI = "sqlite://"

CONFIG = {"modalidades": [
    {
        "nombre": "COMBATE", "tipo_llave": "combate", "activa": True,
        "categorias": {
            "genero": "separado",
            "cinturon": [{"activa": True, "valor": "Todos",
                          "grupos": ["BLANCO", "PRINCIPIANTE", "INTERMEDIO", "AVANZADO", "NEGRO"]}],
            "edad": [{"activa": True, "tipo": "rango", "desde": "10", "hasta": "17"}],
            "peso": [],
        },
    },
    {
        "nombre": "FIGURA CON ARMAS", "tipo_llave": "figuras", "activa": True,
        "categorias": {
            "genero": "separado",
            "cinturon": [{"activa": True, "valor": "Todos",
                          "grupos": ["BLANCO", "PRINCIPIANTE", "INTERMEDIO", "AVANZADO", "NEGRO"]}],
            "edad": [{"activa": True, "tipo": "rango", "desde": "10", "hasta": "17"}],
            "peso": [],
        },
    },
]}


@pytest.fixture()
def entorno():
    app = create_app("development")
    with app.app_context():
        db.create_all()
        from flask_jwt_extended import create_access_token
        from app.models.campeonato import Campeonato
        from app.models.competidor import Competidor, Inscripcion
        from app.models.tatami import Tatami
        from app.models.usuario import Usuario

        admin = Usuario(email="admin@t.local", nombre="ADMIN", rol="admin",
                        es_superadmin=True, activo=True)
        admin.set_password("x")
        db.session.add(admin)
        db.session.flush()
        camp = Campeonato(nombre="COPA", activo=True, fecha_inicio=date(2026, 10, 9),
                          created_by=admin.id, config_categorias=CONFIG)
        db.session.add(camp)
        db.session.flush()
        db.session.add(Tatami(campeonato_id=camp.id, numero=1))

        uids = {}
        for nombre, nacimiento in (("ANA", date(2012, 5, 1)), ("BEA", date(2013, 2, 1)),
                                   ("CAMI", date(2011, 9, 9))):
            c = Competidor(nombre_completo=nombre, genero="FEMENINO",
                           fecha_nacimiento=nacimiento, grupo_cinturon="INTERMEDIO",
                           club="SUR", activo=True, created_by=admin.id)
            db.session.add(c)
            db.session.flush()
            uids[nombre] = c.uid
            db.session.add(Inscripcion(
                campeonato_id=camp.id, competidor_id=c.id,
                modalidades=["COMBATE", "FIGURA CON ARMAS"],
                grupo_cinturon=c.grupo_cinturon,
            ))
        db.session.commit()
        token = create_access_token(identity=str(admin.id))
        yield app, camp.id, uids, {"Authorization": f"Bearer {token}"}
        db.session.remove()
        db.drop_all()


def _llaves(camp_id):
    from app.models.llave import Llave

    db.session.expire_all()
    return {l.tipo_norm: l for l in Llave.query.filter_by(campeonato_id=camp_id).all()}


def _generar(app, camp_id, cabecera):
    r = app.test_client().post(f"/api/campeonatos/{camp_id}/generar-llaves",
                               json={}, headers=cabecera)
    assert r.status_code == 201, r.get_json()


def _llave_pendiente(camp_id, tipo, comps, nombre="LLAVE"):
    """Una llave pendiente hecha directamente, con el enlace ya puesto."""
    from app.api.llaves import generar_estructura, generar_estructura_figuras
    from app.models.llave import Llave

    estructura = (generar_estructura_figuras(comps) if tipo == "figuras"
                  else generar_estructura(comps))
    llave = Llave(campeonato_id=camp_id, tipo=tipo, nombre=nombre, estado="pendiente",
                  estructura=estructura)
    db.session.add(llave)
    db.session.commit()
    return llave.id


# ── 1 · La generación automática ─────────────────────────────────────────

class TestLaGeneracionEnlaza:
    def test_cada_competidor_de_cada_llave_lleva_su_ficha(self, entorno):
        app, camp_id, uids, cabecera = entorno
        _generar(app, camp_id, cabecera)

        llaves = _llaves(camp_id)
        assert set(llaves) == {"combate", "figuras"}
        for llave in llaves.values():
            comps = llave.estructura["competidores"]
            assert {c["nombre"]: c["competidor_uid"] for c in comps} == uids

    def test_el_cuadro_hereda_el_enlace(self, entorno):
        # Los partidos guardan el mismo competidor: de ahí sale el podio.
        app, camp_id, uids, cabecera = entorno
        _generar(app, camp_id, cabecera)

        rondas = _llaves(camp_id)["combate"].estructura["rondas"]
        en_el_cuadro = [
            p[slot] for p in rondas[0] for slot in ("comp1", "comp2") if p[slot]
        ]
        assert en_el_cuadro
        assert all(c["competidor_uid"] == uids[c["nombre"]] for c in en_el_cuadro)


# ── 2 · Re-sortear no pierde el enlace ───────────────────────────────────

class TestReSortearNoLoPierde:
    def test_combinar(self, entorno):
        app, camp_id, uids, cabecera = entorno
        a = _llave_pendiente(camp_id, "figuras", [
            {"nombre": "ANA", "club": "SUR", "competidor_uid": uids["ANA"]},
            {"nombre": "BEA", "club": "SUR", "competidor_uid": uids["BEA"]},
        ])
        b = _llave_pendiente(camp_id, "figuras", [
            {"nombre": "CAMI", "club": "SUR", "competidor_uid": uids["CAMI"]},
            {"nombre": "BEA", "club": "SUR", "competidor_uid": uids["BEA"]},
        ], nombre="OTRA")

        r = app.test_client().post("/api/llaves/combinar",
                                   json={"llave_ids": [a, b]}, headers=cabecera)

        assert r.status_code in (200, 201), r.get_json()
        comps = r.get_json()["llave"]["estructura"]["competidores"]
        assert {c["nombre"]: c.get("competidor_uid") for c in comps} == uids

    def test_mover(self, entorno):
        app, camp_id, uids, cabecera = entorno
        origen = _llave_pendiente(camp_id, "figuras", [
            {"nombre": n, "club": "SUR", "competidor_uid": uids[n]} for n in ("ANA", "BEA", "CAMI")
        ])
        destino = _llave_pendiente(camp_id, "figuras", [
            {"nombre": "DORA", "club": "SUR"}, {"nombre": "EVA", "club": "SUR"},
        ], nombre="DESTINO")
        from app.models.llave import Llave
        id_ana = next(c["id"] for c in Llave.query.get(origen).estructura["competidores"]
                      if c["nombre"] == "ANA")

        r = app.test_client().post("/api/llaves/mover-competidor", headers=cabecera, json={
            "origen_id": origen, "destino_id": destino, "competidor_id": id_ana,
        })

        assert r.status_code == 200, r.get_json()
        db.session.expire_all()
        movida = next(c for c in Llave.query.get(destino).estructura["competidores"]
                      if c["nombre"] == "ANA")
        assert movida["competidor_uid"] == uids["ANA"]
        quedan = Llave.query.get(origen).estructura["competidores"]
        assert all(c["competidor_uid"] == uids[c["nombre"]] for c in quedan)

    def test_editar_conserva_el_de_quien_sigue(self, entorno):
        # El formulario solo manda nombres: sin esto, añadir UN competidor le
        # quitaba el enlace a todos los demás.
        app, camp_id, uids, cabecera = entorno
        lid = _llave_pendiente(camp_id, "figuras", [
            {"nombre": n, "club": "SUR", "competidor_uid": uids[n]} for n in ("ANA", "BEA", "CAMI")
        ])

        r = app.test_client().put(f"/api/llaves/{lid}", headers=cabecera, json={
            "competidores": [{"nombre": n, "club": "SUR"} for n in ("ANA", "BEA", "CAMI", "DORA")],
        })

        assert r.status_code == 200, r.get_json()
        comps = {c["nombre"]: c.get("competidor_uid")
                 for c in r.get_json()["llave"]["estructura"]["competidores"]}
        assert comps == {**uids, "DORA": None}

    def test_editar_con_homonimos_no_adivina(self, entorno):
        # Dos «ANA · SUR» con fichas distintas: ninguna recupera el enlace.
        # Colgarle un resultado a la persona equivocada es peor que no colgarlo.
        app, camp_id, uids, cabecera = entorno
        lid = _llave_pendiente(camp_id, "figuras", [
            {"nombre": "ANA", "club": "SUR", "competidor_uid": uids["ANA"]},
            {"nombre": "ANA", "club": "SUR", "competidor_uid": uids["BEA"]},
            {"nombre": "CAMI", "club": "SUR", "competidor_uid": uids["CAMI"]},
        ])

        r = app.test_client().put(f"/api/llaves/{lid}", headers=cabecera, json={
            "competidores": [{"nombre": n, "club": "SUR"} for n in ("ANA", "ANA", "CAMI", "DORA")],
        })

        assert r.status_code == 200, r.get_json()
        comps = r.get_json()["llave"]["estructura"]["competidores"]
        assert [c.get("competidor_uid") for c in comps if c["nombre"] == "ANA"] == [None, None]
        assert next(c for c in comps if c["nombre"] == "CAMI")["competidor_uid"] == uids["CAMI"]


# ── 3 · La llave hecha a mano ────────────────────────────────────────────

def test_una_llave_hecha_a_mano_sigue_sin_enlace(entorno):
    app, camp_id, _, cabecera = entorno
    r = app.test_client().post("/api/llaves", headers=cabecera, json={
        "campeonato_id": camp_id, "tipo": "figuras", "nombre": "A MANO",
        "competidores": [{"nombre": "X"}, {"nombre": "Y"}, {"nombre": "Z"}],
    })
    assert r.status_code == 201, r.get_json()
    assert all("competidor_uid" not in c for c in r.get_json()["llave"]["estructura"]["competidores"])


# ── 4 · Lo público no enseña el uid ──────────────────────────────────────

def _llave_con_campeon(uid_a="uid-ana", uid_b="uid-bea"):
    a = {"id": 1, "nombre": "ANA", "club": "SUR", "competidor_uid": uid_a}
    b = {"id": 2, "nombre": "BEA", "club": "SUR", "competidor_uid": uid_b}
    return {"competidores": [a, b], "rondas": [[{"comp1": a, "comp2": b, "ganador": 1}]],
            "campeon": a}


def test_el_podio_solo_lleva_el_uid_si_se_pide():
    from app.api.llaves import podio_llave

    estructura = _llave_con_campeon()
    assert all("competidor_uid" not in p for p in podio_llave(estructura))
    con = podio_llave(estructura, con_uid=True)
    assert [(p["puesto"], p["competidor_uid"]) for p in con] == [(1, "uid-ana"), (2, "uid-bea")]


def test_los_resultados_publicos_no_ensenan_el_enlace(entorno):
    app, camp_id, _, _ = entorno
    from app.models.llave import Llave

    db.session.add(Llave(campeonato_id=camp_id, tipo="combate", nombre="FINAL",
                         estado="terminada", estructura=_llave_con_campeon()))
    db.session.commit()

    r = app.test_client().get(f"/api/resultados/campeonato/{camp_id}")

    assert r.status_code == 200
    assert "ANA" in r.get_data(as_text=True)
    assert "competidor_uid" not in r.get_data(as_text=True)


def test_el_archivo_que_viaja_a_internet_si_lleva_el_enlace(entorno):
    """El archivo de resultados (USB o cartero) no es público: lleva el uid.

    Sin él, lo competido en el PC del evento llegaba a internet solo con
    nombres y el panel del competidor lo enseñaba «sin confirmar».
    """
    app, camp_id, _, _ = entorno
    from app.api.resultados import sobre_de_resultados
    from app.models.campeonato import Campeonato
    from app.models.llave import Llave

    db.session.add(Llave(campeonato_id=camp_id, tipo="combate", nombre="FINAL",
                         estado="terminada", estructura=_llave_con_campeon()))
    db.session.commit()

    sobre = sobre_de_resultados(db.session.get(Campeonato, camp_id))
    (final,) = [r for r in sobre["resultados"] if r["nombre"] == "FINAL"]
    assert [(p["puesto"], p.get("competidor_uid")) for p in final["podio"]] == [
        (1, "uid-ana"), (2, "uid-bea"),
    ]


def test_lo_publicado_tampoco_ensena_el_enlace(entorno):
    """Se guarda con el uid (el panel lo lee) y se sirve sin él."""
    app, camp_id, _, cabecera = entorno
    from app.api.resultados import sobre_de_resultados
    from app.models.campeonato import Campeonato
    from app.models.llave import Llave

    db.session.add(Llave(campeonato_id=camp_id, tipo="combate", nombre="FINAL",
                         estado="terminada", estructura=_llave_con_campeon()))
    db.session.commit()
    sobre = sobre_de_resultados(db.session.get(Campeonato, camp_id))
    cliente = app.test_client()
    assert cliente.post("/api/resultados/importar", json=sobre, headers=cabecera).status_code == 200

    r = cliente.get(f"/api/resultados/campeonato/pub:{sobre['export_uuid']}")

    assert r.status_code == 200
    assert "ANA" in r.get_data(as_text=True)
    assert "competidor_uid" not in r.get_data(as_text=True)


# ── 5 · Figuras: el enlace entra por el servidor ─────────────────────────

class TestFiguras:
    def test_la_carga_desde_la_llave_pone_el_enlace_y_el_ranking_lo_hereda(self):
        from app.engine.figuras_engine import calcular_ranking, estado_inicial_figuras, guardar_figuras_snapshot
        from app.sockets.combate_ns import _competidores_de_llave_a_figuras

        estado = estado_inicial_figuras()
        _competidores_de_llave_a_figuras(estado, [
            {"nombre": "ANA", "club": "SUR", "competidor_uid": "uid-ana"},
            {"nombre": "LIBRE", "club": "SUR"},
        ])

        assert [c.get("competidor_uid") for c in estado["competidores"]] == ["uid-ana", None]
        assert {r["nombre"]: r.get("competidor_uid") for r in calcular_ranking(estado)} == {
            "ANA": "uid-ana", "LIBRE": None,
        }
        assert any(r.get("competidor_uid") == "uid-ana"
                   for r in guardar_figuras_snapshot(estado)["ranking"])

    def test_un_nombre_descartado_no_le_pasa_el_enlace_al_anterior(self):
        from app.engine.figuras_engine import estado_inicial_figuras
        from app.sockets.combate_ns import _competidores_de_llave_a_figuras

        estado = estado_inicial_figuras()
        _competidores_de_llave_a_figuras(estado, [
            {"nombre": "ANA", "club": "SUR"},
            {"nombre": "", "club": "SUR", "competidor_uid": "uid-fantasma"},
        ])

        assert [c.get("competidor_uid") for c in estado["competidores"]] == [None]

    def test_un_cliente_no_puede_colgar_un_resultado_a_otra_ficha(self):
        # El evento `agregar_competidor` llega del cliente: el motor no lee el
        # uid de ahí, así que mandarlo no enlaza nada.
        from app.engine.figuras_engine import aplicar_evento_figuras, estado_inicial_figuras

        estado = estado_inicial_figuras()
        aplicar_evento_figuras(estado, {
            "accion": "agregar_competidor", "nombre": "INTRUSO", "club": "X",
            "competidor_uid": "uid-de-otra-persona",
        })

        assert "competidor_uid" not in estado["competidores"][0]
