"""
Test de integración: combate de eliminación controlado por el Juez Central
vía Socket.IO (activar → puntuar → guardar → el ganador avanza en la llave).

Usa una base de datos SQLite en memoria y el test client de Flask-SocketIO.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import create_app  # noqa: E402
from app.config import DevelopmentConfig  # noqa: E402
from app.extensions import db, socketio  # noqa: E402

# Base en memoria, aislada del dinamyt.db local. Debe fijarse ANTES de
# create_app porque Flask-SQLAlchemy construye el engine en init_app.
DevelopmentConfig.SQLALCHEMY_DATABASE_URI = "sqlite://"


@pytest.fixture(autouse=True)
def _quien_puntua_se_identifica(monkeypatch):
    """Desde el 25 sep 2026 quien puntúa tiene que identificarse (ver
    `combate_ns._motivo_para_no_puntuar`). Estas pruebas van del MOTOR, no de
    la puerta —esa tiene las suyas en `test_quien_puntua.py`—: si una conexión
    no trae identidad, entra como superadmin, que puede cualquier papel."""
    original = socketio.test_client

    def con_identidad(app, *args, **kwargs):
        if "auth" not in kwargs:
            from flask_jwt_extended import create_access_token
            from app.models.usuario import Usuario

            with app.app_context():
                jefe = Usuario.query.filter_by(email="super-socket@test.com").first()
                if jefe is None:
                    jefe = Usuario(email="super-socket@test.com", nombre="SUPER",
                                   rol="admin", es_superadmin=True, activo=True)
                    jefe.set_password("x")
                    db.session.add(jefe)
                    db.session.commit()
                kwargs["auth"] = {"token": create_access_token(identity=str(jefe.id))}
        return original(app, *args, **kwargs)

    monkeypatch.setattr(socketio, "test_client", con_identidad)


@pytest.fixture()
def entorno(tmp_path):
    """App + DB en memoria con campeonato, tatami y llave de 2 competidores."""
    app = create_app("development")
    assert "dinamyt.db" not in str(app.config["SQLALCHEMY_DATABASE_URI"])

    # Aislar la persistencia de tatamis: ni leer ni escribir el archivo real
    # (instance/tatami_states.json) que usa el servidor de desarrollo.
    from app.sockets import combate_ns
    combate_ns._SNAPSHOT_PATH = tmp_path / "tatami_states_test.json"
    combate_ns._snapshots_cargados = True

    with app.app_context():
        db.create_all()
        from app.seeds.seed_categorias import seed_categorias
        seed_categorias()

        from app.models.campeonato import Campeonato
        from app.models.tatami import Tatami
        from app.models.llave import Llave
        from app.api.llaves import generar_estructura

        camp = Campeonato(nombre="Camp Test", activo=True)
        db.session.add(camp)
        db.session.flush()
        tatami = Tatami(campeonato_id=camp.id, numero=1)
        db.session.add(tatami)
        db.session.flush()
        llave = Llave(
            campeonato_id=camp.id,
            tatami_id=tatami.id,
            nombre="Llave Test",
            estructura=generar_estructura([{"nombre": "Ana"}, {"nombre": "Luis"}]),
        )
        db.session.add(llave)
        db.session.commit()

        # Estado limpio del tatami para cada test
        from app.sockets import combate_ns
        combate_ns.tatami_states.clear()

        yield app, tatami.id, llave.id
        db.session.remove()
        db.drop_all()


def _ultimo_estado(cliente):
    """Último broadcast de estado recibido por el cliente."""
    estados = [
        r["args"][0]["datos"] for r in cliente.get_received("/combate")
        if r["name"] in ("estado", "estado_confirmado") and r["args"]
    ]
    return estados[-1] if estados else None


def _rechazos(cliente):
    return [
        r["args"][0]["message"] for r in cliente.get_received("/combate")
        if r["name"] == "accion_rechazada" and r["args"]
    ]


_contador_ev = {"n": 0}

_jueces = {}


def _j1(app, tatami_id):
    """La conexión del Juez 1 del tatami (una por prueba y tatami).

    El punto de un juez lo manda SU conexión: desde el 25 sep 2026 el servidor
    no acepta un `punto_juez` a nombre de otro (`JUEZ_DEL_EVENTO`).
    """
    clave = (id(app), tatami_id)
    if clave not in _jueces:
        _jueces[clave] = socketio.test_client(
            app, namespace="/combate", query_string=f"tatami_id={tatami_id}&rol=j1",
        )
    return _jueces[clave]


def _emitir(cliente, accion, **datos):
    # evId único: si se repite, la deduplicación del servidor lo descarta
    _contador_ev["n"] += 1
    ev_id = f"t_{accion}_{_contador_ev['n']}"
    cliente.emit("evento", {"evId": ev_id, "evento": {"accion": accion, **datos}}, namespace="/combate")


class TestCombateEliminacionSocket:
    def test_flujo_completo(self, entorno):
        app, tatami_id, llave_id = entorno
        cliente = socketio.test_client(
            app, namespace="/combate",
            query_string=f"tatami_id={tatami_id}&rol=arbitro",
        )
        assert cliente.is_connected("/combate")

        _emitir(cliente, "activar_tatami")
        _emitir(cliente, "activar_combate_llave", llave_id=llave_id)
        estado = _ultimo_estado(cliente)
        assert estado is not None
        # El broadcast lleva el campeonato (lo usa el botón Volver del admin)
        assert estado["_campeonato_id"] is not None
        assert estado["_tatami_numero"] == 1
        # Nombres autocompletados desde la llave y crono pausado
        assert {estado["nombreHong"], estado["nombreChung"]} == {"Ana", "Luis"}
        assert estado["activo"] is False
        assert estado["_combate_llave"]["llave_id"] == llave_id
        assert estado["_combate_llave"]["ronda_nombre"] == "Final"
        hong_nombre = estado["nombreHong"]

        # Al activar, el público ve el árbol de la llave
        assert estado["_mostrar_arbol"] is True
        assert estado["_hay_arbol"] is True
        assert estado["_llave_arbol"]["nombre"] == "Llave Test"
        assert estado["_llave_arbol"]["estructura"]["campeon"] is None

        # Al iniciar el cronómetro, el público pasa al marcador
        _emitir(cliente, "crono_start")
        estado = _ultimo_estado(cliente)
        assert estado["_mostrar_arbol"] is False
        assert estado["_llave_arbol"] is None, "la estructura no viaja si no se muestra"
        assert estado["_hay_arbol"] is True, "el JC conserva el botón de mostrar árbol"
        _emitir(cliente, "crono_pause")

        # El Juez Central puede volver a mostrar el árbol manualmente
        _emitir(cliente, "mostrar_arbol", mostrar=True)
        estado = _ultimo_estado(cliente)
        assert estado["_mostrar_arbol"] is True

        # Hong anota y el Juez Central guarda → el ganador avanza
        _emitir(_j1(app, tatami_id), "punto_juez", juez="j1", color="hong", pts=2, nombre="Cuerpo")
        _emitir(cliente, "nuevo_combate")
        estado = _ultimo_estado(cliente)
        assert estado["_combate_llave"] is None, "el tatami queda libre tras guardar"
        # El público vuelve a ver el árbol, ya actualizado con el campeón
        assert estado["_mostrar_arbol"] is True
        assert estado["_llave_arbol"]["estructura"]["campeon"] is not None

        with app.app_context():
            from app.models.llave import Llave
            llave = Llave.query.get(llave_id)
            campeon = llave.estructura.get("campeon")
            assert campeon is not None
            assert campeon["nombre"] == hong_nombre, "gana quien estaba como Hong"

        cliente.disconnect(namespace="/combate")

    def test_empate_rechazado(self, entorno):
        app, tatami_id, llave_id = entorno
        cliente = socketio.test_client(
            app, namespace="/combate",
            query_string=f"tatami_id={tatami_id}&rol=arbitro",
        )
        _emitir(cliente, "activar_tatami")
        _emitir(cliente, "activar_combate_llave", llave_id=llave_id)
        cliente.get_received("/combate")

        # Puntos iguales para ambos → guardar debe rechazarse
        _emitir(_j1(app, tatami_id), "punto_juez", juez="j1", color="hong", pts=2, nombre="x")
        _emitir(_j1(app, tatami_id), "punto_juez", juez="j1", color="chung", pts=2, nombre="x")
        _emitir(cliente, "nuevo_combate")
        rechazos = _rechazos(cliente)
        assert any("ganador" in m.lower() for m in rechazos), rechazos

        with app.app_context():
            from app.models.llave import Llave
            llave = Llave.query.get(llave_id)
            assert llave.estructura.get("campeon") is None, "no debe avanzar sin ganador"

        cliente.disconnect(namespace="/combate")

    def test_soltar_combate(self, entorno):
        app, tatami_id, llave_id = entorno
        cliente = socketio.test_client(
            app, namespace="/combate",
            query_string=f"tatami_id={tatami_id}&rol=arbitro",
        )
        _emitir(cliente, "activar_tatami")
        _emitir(cliente, "activar_combate_llave", llave_id=llave_id)
        _emitir(cliente, "soltar_combate_llave")
        estado = _ultimo_estado(cliente)
        assert estado["_combate_llave"] is None

        with app.app_context():
            from app.models.llave import Llave
            llave = Llave.query.get(llave_id)
            assert llave.estructura.get("campeon") is None, "el combate sigue pendiente"
            # Soltar devuelve la llave a la cola: si quedara 'activa' ya no se
            # podría editar, combinar ni re-sortear nunca más.
            assert llave.estado == "pendiente"

        cliente.disconnect(namespace="/combate")

    def test_reset_libera_la_llave(self, entorno):
        """
        Regresión: activar una llave, NO disputarla y resetear dejaba el
        tatami enganchado al partido. El siguiente combate que se guardara
        —aunque fuera de otros competidores— marcaba ganador en el cuadro.
        """
        app, tatami_id, llave_id = entorno
        cliente = socketio.test_client(
            app, namespace="/combate",
            query_string=f"tatami_id={tatami_id}&rol=arbitro",
        )
        _emitir(cliente, "activar_tatami")
        _emitir(cliente, "activar_combate_llave", llave_id=llave_id)
        _emitir(cliente, "reset")
        estado = _ultimo_estado(cliente)
        assert estado["_combate_llave"] is None, "el reset desengancha la llave"

        # Combate suelto de OTROS competidores, guardado después
        _emitir(cliente, "nombres", nombreHong="Pedro", nombreChung="Juan")
        _emitir(_j1(app, tatami_id), "punto_juez", juez="j1", color="hong", pts=2, nombre="x")
        _emitir(cliente, "nuevo_combate")

        with app.app_context():
            from app.models.llave import Llave
            llave = Llave.query.get(llave_id)
            assert llave.estructura.get("campeon") is None, (
                "un combate ajeno no puede coronar campeón en la llave"
            )
            assert all(
                p.get("ganador") is None
                for ronda in llave.estructura["rondas"] for p in ronda
            ), "ningún partido debe quedar marcado"
            assert llave.estado == "pendiente"

        cliente.disconnect(namespace="/combate")

    def test_cambiar_nombres_libera_la_llave(self, entorno):
        """Renombrar a los competidores rompe el vínculo con el cuadro."""
        app, tatami_id, llave_id = entorno
        cliente = socketio.test_client(
            app, namespace="/combate",
            query_string=f"tatami_id={tatami_id}&rol=arbitro",
        )
        _emitir(cliente, "activar_tatami")
        _emitir(cliente, "activar_combate_llave", llave_id=llave_id)
        _emitir(cliente, "nombres", nombreHong="Otro", nombreChung="Distinto")
        estado = _ultimo_estado(cliente)
        assert estado["_combate_llave"] is None

        _emitir(_j1(app, tatami_id), "punto_juez", juez="j1", color="hong", pts=2, nombre="x")
        _emitir(cliente, "nuevo_combate")
        with app.app_context():
            from app.models.llave import Llave
            llave = Llave.query.get(llave_id)
            assert llave.estructura.get("campeon") is None
            assert llave.estado == "pendiente"

        cliente.disconnect(namespace="/combate")

    def test_cambiar_categoria_libera_la_llave(self, entorno):
        """Irse a Figuras y volver no puede dejar el partido enganchado."""
        app, tatami_id, llave_id = entorno
        cliente = socketio.test_client(
            app, namespace="/combate",
            query_string=f"tatami_id={tatami_id}&rol=arbitro",
        )
        _emitir(cliente, "activar_tatami")
        _emitir(cliente, "activar_combate_llave", llave_id=llave_id)
        _emitir(cliente, "cambiar_categoria", categoria="figuras")
        _emitir(cliente, "cambiar_categoria", categoria="combate")
        _emitir(cliente, "nombres", nombreHong="Pedro", nombreChung="Juan")
        _emitir(_j1(app, tatami_id), "punto_juez", juez="j1", color="hong", pts=2, nombre="x")
        _emitir(cliente, "nuevo_combate")

        with app.app_context():
            from app.models.llave import Llave
            llave = Llave.query.get(llave_id)
            assert llave.estructura.get("campeon") is None
            assert llave.estado == "pendiente"

        cliente.disconnect(namespace="/combate")

    def test_eliminar_llave_responde_200(self, entorno):
        """Regresión: eliminar accedía al objeto borrado y respondía 500."""
        app, _tatami_id, llave_id = entorno
        with app.app_context():
            from flask_jwt_extended import create_access_token
            from app.models.usuario import Usuario

            admin = Usuario(email="admin@test.com", nombre="Admin", rol="admin",
                            activo=True, es_superadmin=True)
            admin.set_password("clave-test")
            db.session.add(admin)
            db.session.commit()
            token = create_access_token(identity=str(admin.id))

        cliente = app.test_client()
        resp = cliente.delete(
            f"/api/llaves/{llave_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.get_json()
        assert "eliminada" in resp.get_json()["message"]

        with app.app_context():
            from app.models.llave import Llave
            assert Llave.query.get(llave_id) is None

    def test_no_activa_con_combate_en_curso(self, entorno):
        app, tatami_id, llave_id = entorno
        cliente = socketio.test_client(
            app, namespace="/combate",
            query_string=f"tatami_id={tatami_id}&rol=arbitro",
        )
        _emitir(cliente, "activar_tatami")
        # Combate suelto con nombres y un punto registrado
        _emitir(cliente, "nombres", nombreHong="Pedro", nombreChung="Juan")
        _emitir(_j1(app, tatami_id), "punto_juez", juez="j1", color="hong", pts=1, nombre="x")
        cliente.get_received("/combate")

        _emitir(cliente, "activar_combate_llave", llave_id=llave_id)
        rechazos = _rechazos(cliente)
        assert any("guarda o resetea" in m.lower() for m in rechazos), rechazos

        cliente.disconnect(namespace="/combate")


def _crear_llave_figuras(
    app, tatami_id, nombre="FIGURA CON ARMAS",
    descripcion="Intermedios 15-17 anios", comps=None, asignar=True,
):
    comps = comps or [{"nombre": "Ana"}, {"nombre": "Luis"}, {"nombre": "Mia"}]
    with app.app_context():
        from app.models.tatami import Tatami
        from app.models.llave import Llave
        from app.api.llaves import generar_estructura_figuras

        tatami = Tatami.query.get(tatami_id)
        llave = Llave(
            campeonato_id=tatami.campeonato_id,
            tatami_id=tatami_id if asignar else None,
            tipo="figuras",
            nombre=nombre,
            descripcion=descripcion,
            estado="pendiente",
            estructura=generar_estructura_figuras(comps),
        )
        db.session.add(llave)
        db.session.commit()
        return llave.id


def _token_admin(app):
    with app.app_context():
        from flask_jwt_extended import create_access_token
        from app.models.usuario import Usuario

        admin = Usuario.query.filter_by(email="admin@test.com").first()
        if not admin:
            # Superadmin: opera sobre cualquier workspace (sin scoping por dueño).
            admin = Usuario(email="admin@test.com", nombre="Admin", rol="admin",
                            activo=True, es_superadmin=True)
            admin.set_password("clave-test")
            db.session.add(admin)
            db.session.commit()
        return create_access_token(identity=str(admin.id))


def test_podio_llave_combate():
    from app.api.llaves import (
        generar_estructura, registrar_resultado, podio_llave, partidos_jugables, BRONCE,
    )

    est = generar_estructura([
        {"nombre": "A"}, {"nombre": "B"}, {"nombre": "C"}, {"nombre": "D"},
    ])
    assert podio_llave(est) == [], "sin campeón no hay podio"

    # Semifinales (ronda 0): siempre gana el comp1
    registrar_resultado(est, 0, 0, 1)
    registrar_resultado(est, 0, 1, 1)
    # Tras las semifinales aparece el partido por el bronce
    assert any(r == BRONCE for r, _i, _p in partidos_jugables(est))

    # Final (ronda 1): aún sin bronce → solo 1° y 2°
    registrar_resultado(est, 1, 0, 1)
    assert est["campeon"] is not None
    assert sorted(p["puesto"] for p in podio_llave(est)) == [1, 2]

    # Partido por el bronce → podio con un único 1°, 2° y 3°
    registrar_resultado(est, BRONCE, 0, 1)
    assert partidos_jugables(est) == [], "ya no quedan partidos"
    podio = podio_llave(est)
    assert sorted(p["puesto"] for p in podio) == [1, 2, 3]
    primero = next(p for p in podio if p["puesto"] == 1)
    assert primero["nombre"] == est["campeon"]["nombre"]


def test_podio_llave_con_bye():
    """3 competidores: un bye → un solo 3° puesto (el bye no deja perdedor)."""
    from app.api.llaves import generar_estructura, podio_llave, siguiente_partido, registrar_resultado

    est = generar_estructura([{"nombre": "A"}, {"nombre": "B"}, {"nombre": "C"}])
    # Jugar todos los partidos disponibles dando la victoria al primer lado
    while True:
        sig = siguiente_partido(est)
        if sig is None:
            break
        r, p, _ = sig
        registrar_resultado(est, r, p, 1)
    assert est["campeon"] is not None
    podio = podio_llave(est)
    puestos = sorted(p["puesto"] for p in podio)
    assert puestos == [1, 2, 3], f"esperado 1/2/3, fue {puestos}"


def test_registro_local_propuesto_y_aplicado(entorno):
    """
    Un juez de esquina reconecta y envía su registro local; la mesa (JC) lo
    aplica y los puntos entran al marcador. Las entradas inválidas se filtran.
    """
    app, tatami_id, _llave_id = entorno
    arbitro = socketio.test_client(
        app, namespace="/combate", query_string=f"tatami_id={tatami_id}&rol=arbitro",
    )
    j1 = socketio.test_client(
        app, namespace="/combate", query_string=f"tatami_id={tatami_id}&rol=j1",
    )

    _emitir(arbitro, "activar_tatami")
    _emitir(arbitro, "nombres", nombreHong="Ana", nombreChung="Luis")

    _emitir(j1, "proponer_registro_local", entradas=[
        {"ts": 1, "etiqueta": "+2 GIRO / PAT. CABEZA", "color": "hong", "pts": 2},
        {"ts": 2, "etiqueta": "+1 CUERPO", "color": "chung", "pts": 1},
        {"ts": 3, "etiqueta": "basura", "color": "verde", "pts": 5},   # se filtra
        {"ts": 4, "etiqueta": "basura", "color": "hong", "pts": "x"},  # se filtra
    ])
    estado = _ultimo_estado(arbitro)
    assert "j1" in estado["_propuestas_local"]
    assert len(estado["_propuestas_local"]["j1"]["entradas"]) == 2

    # Solo el Juez Central puede resolver
    _emitir(j1, "resolver_registro_local", rol="j1", aplicar=True)
    estado = _ultimo_estado(arbitro) or estado
    assert estado["jueces"]["j1"]["hong"] == 0, "un juez no puede auto-aplicarse"

    # La mesa lo aplica: los puntos entran al marcador con su detalle
    _emitir(arbitro, "resolver_registro_local", rol="j1", aplicar=True)
    estado = _ultimo_estado(arbitro)
    assert estado["_propuestas_local"] == {}
    assert estado["jueces"]["j1"]["hong"] == 2
    assert estado["jueces"]["j1"]["chung"] == 1
    assert any("APLICADO" in l["txt"] for l in estado["log"])

    # El juez recibe la resolución (su libreta local se limpia sola)
    resueltos = [
        r for r in j1.get_received("/combate")
        if r["name"] == "registro_local_resuelto"
    ]
    assert resueltos and resueltos[-1]["args"][0]["aplicado"] is True


def test_bronce_espera_a_la_otra_semifinal():
    """
    Con 4 competidores, al caer el PRIMER semifinalista el bronce NO se
    adjudica: queda en espera del perdedor de la otra semifinal. (Antes se
    marcaba 3° automático como si la semifinal pendiente fuera un bye.)
    """
    from app.api.llaves import generar_estructura, registrar_resultado

    est = generar_estructura([
        {"nombre": "A"}, {"nombre": "B"}, {"nombre": "C"}, {"nombre": "D"},
    ])
    registrar_resultado(est, 0, 0, 1)  # primera semifinal jugada
    bronce = est.get("bronce")
    assert bronce is not None
    assert bronce["comp1"] is not None
    assert bronce["comp2"] is None, "el rival sale de la otra semifinal"
    assert bronce["ganador"] is None, "el 3° no puede adjudicarse aún"

    registrar_resultado(est, 0, 1, 1)  # segunda semifinal jugada
    bronce = est["bronce"]
    assert bronce["comp1"] and bronce["comp2"]
    assert bronce["ganador"] is None, "el bronce queda por disputarse"


def test_no_se_marca_ganador_sin_rival_definido():
    """En rondas > 1, marcar ganador con el rival aún sin definir se rechaza."""
    from app.api.llaves import generar_estructura, registrar_resultado

    est = generar_estructura([
        {"nombre": "A"}, {"nombre": "B"}, {"nombre": "C"}, {"nombre": "D"},
    ])
    registrar_resultado(est, 0, 0, 1)  # solo una semifinal jugada
    with pytest.raises(ValueError):
        registrar_resultado(est, 1, 0, 1)  # la final espera al otro finalista
    assert est["campeon"] is None


def test_editar_conserva_el_sorteo_si_competidores_no_cambian(entorno):
    """
    PUT /api/llaves/:id reenviando los MISMOS competidores (así lo hace el
    formulario al cambiar solo nombre o tatami) no debe volver a sortear.
    """
    app, tatami_id, _llave_id = entorno
    token = _token_admin(app)
    cliente = app.test_client()
    auth = {"Authorization": f"Bearer {token}"}

    with app.app_context():
        from app.models.tatami import Tatami
        camp_id = Tatami.query.get(tatami_id).campeonato_id

    comps = [{"nombre": n, "club": ""} for n in ("A", "B", "C", "D")]
    resp = cliente.post(
        "/api/llaves",
        json={"campeonato_id": camp_id, "nombre": "Editable", "competidores": comps},
        headers=auth,
    )
    assert resp.status_code == 201
    llave_id = resp.get_json()["llave"]["id"]
    estructura_antes = resp.get_json()["llave"]["estructura"]

    resp = cliente.put(
        f"/api/llaves/{llave_id}",
        json={"nombre": "Nombre Nuevo", "competidores": comps},
        headers=auth,
    )
    assert resp.status_code == 200
    datos = resp.get_json()["llave"]
    assert datos["nombre"] == "Nombre Nuevo"
    assert datos["estructura"] == estructura_antes, "el cuadro no debe re-sortearse"

    # Con una lista DIFERENTE sí se regenera el cuadro
    resp = cliente.put(
        f"/api/llaves/{llave_id}",
        json={"competidores": comps + [{"nombre": "E", "club": ""}]},
        headers=auth,
    )
    assert resp.status_code == 200
    regenerada = resp.get_json()["llave"]["estructura"]
    assert len(regenerada["competidores"]) == 5


class TestGrupoFiguras:
    def test_crear_figuras_via_api(self, entorno):
        app, tatami_id, _ = entorno
        token = _token_admin(app)
        with app.app_context():
            from app.models.tatami import Tatami
            camp_id = Tatami.query.get(tatami_id).campeonato_id

        cliente = app.test_client()
        resp = cliente.post(
            "/api/llaves",
            json={
                "campeonato_id": camp_id,
                "tipo": "figuras",
                "nombre": "DEFENSA PERSONAL",
                "descripcion": "Avanzados 18+",
                # Sin tatami: queda en el pool
                "competidores": [{"nombre": "A"}, {"nombre": "B"}, {"nombre": "C"}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201, resp.get_json()
        llave = resp.get_json()["llave"]
        assert llave["tipo"] == "figuras"
        assert llave["estado"] == "pendiente"
        assert llave["tatami_id"] is None
        assert llave["descripcion"] == "Avanzados 18+"
        assert llave["estructura"]["rondas"] == []
        assert len(llave["estructura"]["competidores"]) == 3

    def test_figuras_minimo_competidores(self, entorno):
        app, tatami_id, _ = entorno
        token = _token_admin(app)
        with app.app_context():
            from app.models.tatami import Tatami
            camp_id = Tatami.query.get(tatami_id).campeonato_id
        cliente = app.test_client()
        resp = cliente.post(
            "/api/llaves",
            json={
                "campeonato_id": camp_id, "tipo": "figuras", "nombre": "X",
                "competidores": [{"nombre": "A"}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_editar_solo_si_pendiente(self, entorno):
        app, tatami_id, _ = entorno
        fig_id = _crear_llave_figuras(app, tatami_id)
        token = _token_admin(app)
        cliente = app.test_client()

        # Pendiente: editar OK (agregar competidor + cambiar descripción)
        resp = cliente.put(
            f"/api/llaves/{fig_id}",
            json={
                "descripcion": "Nueva desc",
                "competidores": [{"nombre": "A"}, {"nombre": "B"}, {"nombre": "C"}, {"nombre": "D"}],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.get_json()
        assert len(resp.get_json()["llave"]["estructura"]["competidores"]) == 4

        # Marcar como activa y reintentar: debe rechazar (409)
        with app.app_context():
            from app.models.llave import Llave
            llave = Llave.query.get(fig_id)
            llave.estado = "activa"
            db.session.commit()
        resp2 = cliente.put(
            f"/api/llaves/{fig_id}",
            json={"descripcion": "no debería"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.status_code == 409

    def test_marcar_ganador_rechaza_figuras(self, entorno):
        app, tatami_id, _ = entorno
        fig_id = _crear_llave_figuras(app, tatami_id)
        token = _token_admin(app)
        cliente = app.test_client()
        resp = cliente.put(
            f"/api/llaves/{fig_id}/partido",
            json={"ronda": 0, "partido": 0, "ganador": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    def test_activar_grupo_figuras_carga_competidores(self, entorno):
        app, tatami_id, _ = entorno
        fig_id = _crear_llave_figuras(app, tatami_id)
        cliente = socketio.test_client(
            app, namespace="/combate",
            query_string=f"tatami_id={tatami_id}&rol=arbitro",
        )
        _emitir(cliente, "activar_tatami")
        _emitir(cliente, "activar_grupo_figuras", llave_id=fig_id)
        estado = _ultimo_estado(cliente)
        assert estado["_categoria"] == "figuras"
        assert estado["nombre_categoria"] == "FIGURA CON ARMAS"
        assert estado.get("descripcion") == "Intermedios 15-17 anios"
        assert len(estado["competidores"]) == 3
        assert estado["_grupo_figuras"]["llave_id"] == fig_id

        with app.app_context():
            from app.models.llave import Llave
            assert Llave.query.get(fig_id).estado == "activa"

        # Guardar la categoría (sin puntuar) → grupo terminado
        _emitir(cliente, "nuevo_combate")
        estado = _ultimo_estado(cliente)
        assert estado.get("_grupo_figuras") is None
        with app.app_context():
            from app.models.llave import Llave
            assert Llave.query.get(fig_id).estado == "terminada"

        cliente.disconnect(namespace="/combate")

    def test_activar_grupo_otro_tatami_rechazado(self, entorno):
        app, tatami_id, _ = entorno
        # Grupo en el pool (sin tatami)
        fig_id = _crear_llave_figuras(app, tatami_id, asignar=False)
        cliente = socketio.test_client(
            app, namespace="/combate",
            query_string=f"tatami_id={tatami_id}&rol=arbitro",
        )
        _emitir(cliente, "activar_tatami")
        _emitir(cliente, "activar_grupo_figuras", llave_id=fig_id)
        rechazos = _rechazos(cliente)
        assert any("otro tatami" in m.lower() for m in rechazos), rechazos
        cliente.disconnect(namespace="/combate")

    def test_soltar_grupo_figuras(self, entorno):
        app, tatami_id, _ = entorno
        fig_id = _crear_llave_figuras(app, tatami_id)
        cliente = socketio.test_client(
            app, namespace="/combate",
            query_string=f"tatami_id={tatami_id}&rol=arbitro",
        )
        _emitir(cliente, "activar_tatami")
        _emitir(cliente, "activar_grupo_figuras", llave_id=fig_id)
        estado = _ultimo_estado(cliente)
        assert estado["_grupo_figuras"]["llave_id"] == fig_id
        with app.app_context():
            from app.models.llave import Llave
            assert Llave.query.get(fig_id).estado == "activa"

        # Soltar: se desvincula y la llave vuelve a 'pendiente'
        _emitir(cliente, "soltar_grupo_figuras")
        estado = _ultimo_estado(cliente)
        assert estado.get("_grupo_figuras") is None
        with app.app_context():
            from app.models.llave import Llave
            assert Llave.query.get(fig_id).estado == "pendiente"
        cliente.disconnect(namespace="/combate")


def test_partido_bronce_via_api(entorno):
    """El 3er puesto se marca por HTTP con ronda='bronce' y cierra la llave."""
    app, tatami_id, _ = entorno
    token = _token_admin(app)
    with app.app_context():
        from app.models.tatami import Tatami
        from app.models.llave import Llave
        from app.api.llaves import generar_estructura
        tatami = Tatami.query.get(tatami_id)
        llave = Llave(
            campeonato_id=tatami.campeonato_id, tatami_id=tatami_id, tipo="combate",
            nombre="LLAVE 4", estado="pendiente",
            estructura=generar_estructura([{"nombre": n} for n in ["A", "B", "C", "D"]]),
        )
        db.session.add(llave)
        db.session.commit()
        lid = llave.id

    cliente = app.test_client()

    def put(ronda, partido, ganador):
        return cliente.put(
            f"/api/llaves/{lid}/partido",
            json={"ronda": ronda, "partido": partido, "ganador": ganador},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert put(0, 0, 1).status_code == 200       # semifinal 1
    assert put(0, 1, 1).status_code == 200       # semifinal 2
    r_final = put(1, 0, 1)                        # final
    assert r_final.status_code == 200
    # Falta el bronce → todavía no terminada
    assert r_final.get_json()["llave"]["estado"] != "terminada"

    rb = put("bronce", 0, 1)                      # partido por el 3er puesto
    assert rb.status_code == 200, rb.get_json()
    llave_json = rb.get_json()["llave"]
    assert llave_json["estructura"]["bronce"]["ganador"] == 1
    assert llave_json["estado"] == "terminada"

    from app.api.llaves import podio_llave
    podio = podio_llave(llave_json["estructura"])
    assert sorted(p["puesto"] for p in podio) == [1, 2, 3]


def test_configurar_combate_sin_activar(entorno):
    """Con el tatami desactivado se puede CONFIGURAR (jueces, nombres) pero NO
    iniciar el cronómetro."""
    app, tatami_id, _ = entorno
    cliente = socketio.test_client(
        app, namespace="/combate",
        query_string=f"tatami_id={tatami_id}&rol=arbitro",
    )
    # SIN activar el tatami: la configuración debe aplicar
    _emitir(cliente, "set_num_jueces", numJueces=2)   # sin nombres aún
    _emitir(cliente, "nombres", nombreHong="Pedro", nombreChung="Juan")
    estado = _ultimo_estado(cliente)
    assert estado["_tatami_activo"] is False
    assert estado["numJueces"] == 2
    assert estado["nombreHong"] == "Pedro"

    # El cronómetro NO arranca sin activar el tatami (acción ignorada)
    cliente.get_received("/combate")
    _emitir(cliente, "crono_start")
    cliente.emit("pedir", namespace="/combate")
    estado = _ultimo_estado(cliente)
    assert estado is not None
    assert estado["activo"] is False
    cliente.disconnect(namespace="/combate")


def test_activar_grupo_figuras_sin_activar(entorno):
    """El grupo de figuras se carga aunque el tatami esté desactivado."""
    app, tatami_id, _ = entorno
    fig_id = _crear_llave_figuras(app, tatami_id)
    cliente = socketio.test_client(
        app, namespace="/combate",
        query_string=f"tatami_id={tatami_id}&rol=arbitro",
    )
    # SIN activar el tatami
    _emitir(cliente, "activar_grupo_figuras", llave_id=fig_id)
    estado = _ultimo_estado(cliente)
    assert estado["_categoria"] == "figuras"
    assert estado["_tatami_activo"] is False
    assert len(estado["competidores"]) == 3
    cliente.disconnect(namespace="/combate")


# ══════════════════════════════════════════════════════════════════
#  Combinar llaves y mover competidores entre llaves (solo pendientes)
# ══════════════════════════════════════════════════════════════════

def _crear_llave_combate(app, tatami_id, nombre, comps, asignar=True):
    """Crea una llave de combate PENDIENTE directamente en la BD."""
    with app.app_context():
        from app.models.tatami import Tatami
        from app.models.llave import Llave
        from app.api.llaves import generar_estructura

        tatami = Tatami.query.get(tatami_id)
        llave = Llave(
            campeonato_id=tatami.campeonato_id,
            tatami_id=tatami_id if asignar else None,
            tipo="combate",
            nombre=nombre,
            estado="pendiente",
            estructura=generar_estructura(comps),
        )
        db.session.add(llave)
        db.session.commit()
        return llave.id


def test_combinar_llaves_une_y_resortea(entorno):
    """Dos llaves pendientes se fusionan en una con todos los competidores."""
    app, tatami_id, base_llave = entorno
    token = _token_admin(app)
    a = _crear_llave_combate(app, tatami_id, "A", [{"nombre": "Ana"}, {"nombre": "Bea"}, {"nombre": "Cami"}])
    b = _crear_llave_combate(app, tatami_id, "B", [{"nombre": "Dario"}, {"nombre": "Elias"}, {"nombre": "Fabi"}])

    cliente = app.test_client()
    resp = cliente.post(
        "/api/llaves/combinar",
        json={"llave_ids": [a, b], "nombre": "UNIDA"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.get_json()
    nueva = resp.get_json()["llave"]
    assert nueva["nombre"] == "UNIDA"
    assert len(nueva["estructura"]["competidores"]) == 6

    with app.app_context():
        from app.models.llave import Llave
        assert Llave.query.get(a) is None, "la llave origen A se elimina"
        assert Llave.query.get(b) is None, "la llave origen B se elimina"


def test_combinar_rechaza_tipos_distintos(entorno):
    """No se puede combinar una llave de combate con un grupo de figuras."""
    app, tatami_id, _ = entorno
    token = _token_admin(app)
    combate = _crear_llave_combate(app, tatami_id, "C", [{"nombre": "A"}, {"nombre": "B"}, {"nombre": "C"}])
    figuras = _crear_llave_figuras(app, tatami_id)

    cliente = app.test_client()
    resp = cliente.post(
        "/api/llaves/combinar",
        json={"llave_ids": [combate, figuras]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "combate" in resp.get_json()["error"].lower()


def test_combinar_rechaza_llave_no_pendiente(entorno):
    """Una llave activa no se puede combinar (protege resultados)."""
    app, tatami_id, _ = entorno
    token = _token_admin(app)
    a = _crear_llave_combate(app, tatami_id, "A", [{"nombre": "A"}, {"nombre": "B"}, {"nombre": "C"}])
    b = _crear_llave_combate(app, tatami_id, "B", [{"nombre": "D"}, {"nombre": "E"}, {"nombre": "F"}])
    with app.app_context():
        from app.models.llave import Llave
        llave = Llave.query.get(a)
        llave.estado = "activa"
        db.session.commit()

    cliente = app.test_client()
    resp = cliente.post(
        "/api/llaves/combinar",
        json={"llave_ids": [a, b]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409


def test_mover_competidor_entre_llaves(entorno):
    """Mover un competidor: sale de la origen y entra en la destino.
    Origen con 4 comps → al quitar 1 quedan 3 (sigue siendo válida)."""
    app, tatami_id, _ = entorno
    token = _token_admin(app)
    origen = _crear_llave_combate(app, tatami_id, "ORIG",
                                  [{"nombre": "Ana"}, {"nombre": "Bea"}, {"nombre": "Cami"}, {"nombre": "Gaby"}])
    destino = _crear_llave_combate(app, tatami_id, "DEST",
                                   [{"nombre": "Dario"}, {"nombre": "Elias"}, {"nombre": "Fabi"}])

    with app.app_context():
        from app.models.llave import Llave
        comp = Llave.query.get(origen).estructura["competidores"][0]
        comp_id, comp_nombre = comp["id"], comp["nombre"]

    cliente = app.test_client()
    resp = cliente.post(
        "/api/llaves/mover-competidor",
        json={"origen_id": origen, "destino_id": destino, "competidor_id": comp_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["origen_eliminada"] is False

    with app.app_context():
        from app.models.llave import Llave
        nombres_origen = [c["nombre"] for c in Llave.query.get(origen).estructura["competidores"]]
        nombres_destino = [c["nombre"] for c in Llave.query.get(destino).estructura["competidores"]]
        assert comp_nombre not in nombres_origen
        assert comp_nombre in nombres_destino
        assert len(nombres_origen) == 3
        assert len(nombres_destino) == 4


def test_mover_rechaza_si_origen_queda_invalida(entorno):
    """Mover de una llave de 3 (el mínimo) la dejaría en 2: se rechaza (409)."""
    app, tatami_id, _ = entorno
    token = _token_admin(app)
    origen = _crear_llave_combate(app, tatami_id, "ORIG", [{"nombre": "Ana"}, {"nombre": "Bea"}, {"nombre": "Cami"}])
    destino = _crear_llave_combate(app, tatami_id, "DEST", [{"nombre": "Dario"}, {"nombre": "Elias"}, {"nombre": "Fabi"}])

    with app.app_context():
        from app.models.llave import Llave
        comp_id = Llave.query.get(origen).estructura["competidores"][0]["id"]

    cliente = app.test_client()
    resp = cliente.post(
        "/api/llaves/mover-competidor",
        json={"origen_id": origen, "destino_id": destino, "competidor_id": comp_id},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409
    assert "combinar" in resp.get_json()["error"].lower()


def test_scoping_admin_no_ve_llaves_de_otro(entorno):
    """Un admin normal no ve las llaves de un campeonato que no creó (404)."""
    app, tatami_id, llave_id = entorno
    with app.app_context():
        from flask_jwt_extended import create_access_token
        from app.models.usuario import Usuario
        from app.models.tatami import Tatami

        camp_id = Tatami.query.get(tatami_id).campeonato_id
        # Admin normal (NO superadmin, NO dueño del campeonato de prueba)
        otro = Usuario(email="otro@test.com", nombre="Otro", rol="admin", activo=True)
        otro.set_password("x")
        db.session.add(otro)
        db.session.commit()
        token_otro = create_access_token(identity=str(otro.id))

    cliente = app.test_client()
    # No ve las llaves del campeonato ajeno
    resp = cliente.get(
        f"/api/llaves/campeonato/{camp_id}",
        headers={"Authorization": f"Bearer {token_otro}"},
    )
    assert resp.status_code == 404
    # Ni el detalle de una llave ajena
    resp2 = cliente.get(
        f"/api/llaves/{llave_id}",
        headers={"Authorization": f"Bearer {token_otro}"},
    )
    assert resp2.status_code == 404
