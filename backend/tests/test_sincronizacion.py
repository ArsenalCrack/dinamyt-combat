"""
Tests del traspaso de un campeonato entre instancias (online → local).

Se simulan DOS instalaciones distintas con dos bases SQLite en disco: la de
ORIGEN (donde se inscribe) exporta el paquete y la de DESTINO (la del evento)
lo importa. Es la única forma de comprobar de verdad lo que importa aquí: que
los ids enteros de una instancia no se mezclen con los de la otra.
"""

import json
import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import create_app  # noqa: E402
from app.config import DevelopmentConfig  # noqa: E402
from app.extensions import db  # noqa: E402


def _app(ruta):
    """App nueva apuntando a su propia base (una instancia del software)."""
    DevelopmentConfig.SQLALCHEMY_DATABASE_URI = f"sqlite:///{ruta}"
    return create_app("development")


def _token(user):
    from flask_jwt_extended import create_access_token

    return create_access_token(
        identity=str(user.id),
        additional_claims={"rol": user.rol, "nombre": user.nombre, "email": user.email},
    )


def _crear_admin(email="admin@test.local"):
    from app.models.usuario import Usuario

    admin = Usuario(email=email, nombre="Admin", rol="admin",
                    es_superadmin=True, activo=True)
    admin.set_password("secret123")
    db.session.add(admin)
    db.session.commit()
    return admin


def _sembrar_origen(admin):
    """Campeonato completo: 2 tatamis, juez asignado, maestro, inscripciones y llave."""
    from app.models.asignacion import AsignacionJuez
    from app.models.campeonato import Campeonato
    from app.models.competidor import Competidor, Inscripcion
    from app.models.llave import Llave
    from app.models.tatami import Tatami
    from app.models.usuario import Usuario

    juez = Usuario(email="juez@test.local", nombre="Juez Uno", rol="juez",
                   activo=True, creado_por_id=admin.id)
    juez.set_password("secret123")
    maestro = Usuario(email="maestro@test.local", nombre="Maestro Dos",
                      rol="maestro", club="Club Sur", delegacion="Cali",
                      pais_delegacion="Colombia", puede_juzgar=True,
                      activo=True, creado_por_id=admin.id)
    maestro.set_password("secret123")
    db.session.add_all([juez, maestro])

    camp = Campeonato(nombre="Copa Nacional", estado="preparacion", activo=True,
                      lugar="Coliseo", ciudad="Cali", pais="Colombia",
                      created_by=admin.id)
    db.session.add(camp)
    db.session.flush()

    t1 = Tatami(campeonato_id=camp.id, numero=1, activo=True)
    t2 = Tatami(campeonato_id=camp.id, numero=2, activo=True)
    db.session.add_all([t1, t2])
    db.session.flush()

    db.session.add(AsignacionJuez(usuario_id=juez.id, tatami_id=t1.id,
                                  rol_tatami="arbitro", nombre_display="Juez Uno"))

    ana = Competidor(nombre_completo="Ana Ruiz", documento="111", genero="FEMENINO",
                     cinturon="Azul", grupo_cinturon="INTERMEDIO", peso=55.0,
                     club="Club Sur", activo=True, created_by=admin.id)
    beto = Competidor(nombre_completo="Beto Paz", documento="222", genero="MASCULINO",
                      cinturon="Verde", grupo_cinturon="INTERMEDIO", peso=61.5,
                      club="Club Norte", activo=True, created_by=admin.id)
    db.session.add_all([ana, beto])
    db.session.flush()

    db.session.add(Inscripcion(campeonato_id=camp.id, competidor_id=ana.id,
                               modalidades=["COMBATE"], peso=55.0,
                               grupo_cinturon="INTERMEDIO", estado="aceptada",
                               created_by=admin.id))
    # Solicitud de un maestro, todavía sin revisar: debe viajar como pendiente.
    db.session.add(Inscripcion(campeonato_id=camp.id, competidor_id=beto.id,
                               modalidades=["COMBATE"], peso=61.5,
                               grupo_cinturon="INTERMEDIO", estado="pendiente",
                               created_by=maestro.id))

    db.session.add(Llave(
        campeonato_id=camp.id, tatami_id=t1.id, tipo="combate",
        nombre="INTERMEDIOS", descripcion="Intermedios 15-17", estado="pendiente",
        seccion_clave="combate|intermedio|15-17", created_by=admin.id,
        estructura={"competidores": [{"nombre": "Ana Ruiz", "club": "Club Sur"}]},
    ))
    db.session.commit()
    return camp.id


@pytest.fixture()
def paquete(tmp_path):
    """Paquete exportado desde la instancia de ORIGEN."""
    app = _app(tmp_path / "origen.db")
    ctx = app.app_context()
    ctx.push()
    db.create_all()
    admin = _crear_admin()
    camp_id = _sembrar_origen(admin)
    resp = app.test_client().get(
        f"/api/sincronizacion/campeonato/{camp_id}/exportar",
        headers={"Authorization": f"Bearer {_token(admin)}"},
    )
    assert resp.status_code == 200
    datos = resp.get_json()
    db.session.remove()
    ctx.pop()
    return datos


@pytest.fixture()
def destino(tmp_path):
    """Instancia de DESTINO vacía, con su propio admin. (app, token)."""
    app = _app(tmp_path / "destino.db")
    ctx = app.app_context()
    ctx.push()
    db.create_all()
    admin = _crear_admin("local@test.local")
    yield app, _token(admin)
    db.session.remove()
    ctx.pop()


def _importar(app, token, paquete, **opciones):
    """Sube el paquete como archivo (el camino real desde el navegador)."""
    datos = {
        "file": (BytesIO(json.dumps(paquete).encode("utf-8")), "campeonato.json"),
    }
    datos.update({k: str(v) for k, v in opciones.items()})
    return app.test_client().post(
        "/api/sincronizacion/importar",
        headers={"Authorization": f"Bearer {token}"},
        data=datos,
        content_type="multipart/form-data",
    )


# ── El paquete exportado ─────────────────────────────────────────────────────

def test_el_paquete_no_lleva_contrasenas_ni_administradores(paquete):
    assert paquete["formato"] == "dinamyt-campeonato"
    assert len(paquete["usuarios"]) == 2
    for u in paquete["usuarios"]:
        assert "password_hash" not in u
        assert "es_superadmin" not in u
        assert u["rol"] in ("maestro", "juez")


def test_el_paquete_lleva_todo_el_campeonato(paquete):
    assert paquete["campeonato"]["nombre"] == "Copa Nacional"
    assert len(paquete["tatamis"]) == 2
    assert len(paquete["asignaciones"]) == 1
    assert len(paquete["competidores"]) == 2
    assert len(paquete["inscripciones"]) == 2
    assert len(paquete["llaves"]) == 1
    # Todo va referenciado por uid, nunca por el id entero de la otra instancia.
    assert paquete["asignaciones"][0]["usuario_uid"]
    assert paquete["asignaciones"][0]["tatami_uid"]


def test_se_puede_excluir_una_seccion(tmp_path):
    app = _app(tmp_path / "origen2.db")
    ctx = app.app_context()
    ctx.push()
    db.create_all()
    admin = _crear_admin()
    camp_id = _sembrar_origen(admin)
    resp = app.test_client().get(
        f"/api/sincronizacion/campeonato/{camp_id}/exportar?llaves=0&usuarios=0",
        headers={"Authorization": f"Bearer {_token(admin)}"},
    )
    datos = resp.get_json()
    db.session.remove()
    ctx.pop()

    assert "llaves" not in datos
    assert "usuarios" not in datos
    assert "competidores" in datos


# ── La importación ───────────────────────────────────────────────────────────

def test_importa_el_campeonato_completo(destino, paquete):
    app, token = destino
    resp = _importar(app, token, paquete)

    assert resp.status_code == 200, resp.get_json()
    cuerpo = resp.get_json()
    assert cuerpo["campeonato"]["nuevo"] is True
    assert cuerpo["resumen"]["usuarios"]["nuevos"] == 2
    assert cuerpo["resumen"]["competidores"]["nuevos"] == 2
    assert cuerpo["resumen"]["inscripciones"]["nuevos"] == 2
    assert cuerpo["resumen"]["llaves"]["nuevos"] == 1

    from app.models.asignacion import AsignacionJuez
    from app.models.campeonato import Campeonato
    from app.models.competidor import Competidor, Inscripcion
    from app.models.llave import Llave
    from app.models.tatami import Tatami

    # "COPA NACIONAL": el nombre se normaliza al importarlo. La ciudad NO —
    # sale del catálogo de geo y se compara con él por valor exacto.
    camp = Campeonato.query.filter_by(nombre="COPA NACIONAL").first()
    assert camp is not None
    assert camp.ciudad == "Cali"
    assert Tatami.query.filter_by(campeonato_id=camp.id).count() == 2
    assert Competidor.query.count() == 2
    assert Inscripcion.query.filter_by(campeonato_id=camp.id).count() == 2
    # El estado de moderación viaja: la del maestro sigue pendiente.
    assert Inscripcion.query.filter_by(estado="pendiente").count() == 1
    assert Llave.query.filter_by(campeonato_id=camp.id).count() == 1

    # La asignación del juez quedó apuntando al juez y al tatami correctos.
    asig = AsignacionJuez.query.one()
    assert asig.usuario.email == "juez@test.local"
    assert asig.tatami.numero == 1
    assert asig.tatami.campeonato_id == camp.id


def test_los_usuarios_llegan_sin_contrasena_utilizable(destino, paquete):
    app, token = destino
    _importar(app, token, paquete)

    from app.models.usuario import Usuario

    juez = Usuario.query.filter_by(email="juez@test.local").first()
    assert juez is not None
    assert juez.rol == "juez"
    # La clave de la otra instancia no sirve aquí: no viajó.
    assert not juez.check_password("secret123")
    assert juez.es_superadmin is False


def test_todo_queda_en_el_workspace_del_admin_que_importa(destino, paquete):
    """Sin esto, lo importado existiría en la base pero el admin no lo vería."""
    app, token = destino
    _importar(app, token, paquete)

    from app.models.campeonato import Campeonato
    from app.models.competidor import Competidor
    from app.models.usuario import Usuario

    admin = Usuario.query.filter_by(email="local@test.local").first()
    assert Campeonato.query.one().created_by == admin.id
    for c in Competidor.query.all():
        assert c.created_by == admin.id
    for u in Usuario.query.filter(Usuario.rol != "admin").all():
        assert u.creado_por_id == admin.id


def test_reimportar_no_duplica_nada(destino, paquete):
    app, token = destino
    _importar(app, token, paquete)
    resp = _importar(app, token, paquete)

    assert resp.status_code == 200
    cuerpo = resp.get_json()
    assert cuerpo["campeonato"]["nuevo"] is False
    assert cuerpo["resumen"]["usuarios"]["nuevos"] == 0
    assert cuerpo["resumen"]["competidores"]["nuevos"] == 0

    from app.models.campeonato import Campeonato
    from app.models.competidor import Competidor, Inscripcion
    from app.models.llave import Llave
    from app.models.tatami import Tatami
    from app.models.usuario import Usuario

    assert Campeonato.query.count() == 1
    assert Tatami.query.count() == 2
    assert Competidor.query.count() == 2
    assert Inscripcion.query.count() == 2
    assert Llave.query.count() == 1
    assert Usuario.query.count() == 3  # admin local + juez + maestro


def test_un_usuario_que_ya_existia_por_correo_se_vincula(destino, paquete):
    """El maestro creado a mano en local no se duplica: se adopta su identidad."""
    app, token = destino
    from app.models.usuario import Usuario

    previo = Usuario(email="maestro@test.local", nombre="Maestro Local",
                     rol="maestro", club="Club Viejo", activo=True)
    previo.set_password("clave-local")
    db.session.add(previo)
    db.session.commit()
    uid_previo = previo.uid

    resp = _importar(app, token, paquete)

    assert resp.status_code == 200
    assert Usuario.query.filter_by(email="maestro@test.local").count() == 1
    maestro = Usuario.query.filter_by(email="maestro@test.local").first()
    # "CLUB SUR": los nombres del paquete se normalizan al importarlos, igual
    # que los que se escriben aquí (ver `_nombre` en api/sincronizacion.py).
    assert maestro.club == "CLUB SUR"          # se actualizó con el paquete
    assert maestro.uid != uid_previo           # adoptó la identidad del paquete
    assert maestro.check_password("clave-local")  # su contraseña NO se tocó


def test_vista_previa_no_escribe_nada(destino, paquete):
    app, token = destino
    resp = _importar(app, token, paquete, vista_previa=1)

    assert resp.status_code == 200
    cuerpo = resp.get_json()
    assert cuerpo["vista_previa"] is True
    # El informe anuncia exactamente lo que haría la importación real...
    assert cuerpo["resumen"]["competidores"]["nuevos"] == 2
    assert cuerpo["resumen"]["llaves"]["nuevos"] == 1

    # ...pero la base sigue intacta.
    from app.models.campeonato import Campeonato
    from app.models.competidor import Competidor
    from app.models.usuario import Usuario

    assert Campeonato.query.count() == 0
    assert Competidor.query.count() == 0
    assert Usuario.query.count() == 1  # solo el admin local


def test_no_pisa_un_evento_ya_empezado(destino, paquete):
    app, token = destino
    _importar(app, token, paquete)

    from app.models.llave import Llave

    # El evento arranca en local: la llave pasa a disputarse.
    llave = Llave.query.one()
    llave.estado = "activa"
    db.session.commit()

    resp = _importar(app, token, paquete)
    assert resp.status_code == 409
    assert "resultados" in resp.get_json()["error"]

    # Con confirmación explícita sí entra, pero la llave disputada se respeta.
    resp = _importar(app, token, paquete, forzar=1)
    assert resp.status_code == 200
    assert Llave.query.one().estado == "activa"


def test_modo_reemplazar_deja_solo_lo_del_paquete(destino, paquete):
    app, token = destino
    _importar(app, token, paquete)

    from app.models.campeonato import Campeonato
    from app.models.competidor import Competidor, Inscripcion

    # Alguien inscribe a mano en local a un atleta que no está en el paquete.
    camp = Campeonato.query.one()
    extra = Competidor(nombre_completo="Extra Local", activo=True)
    db.session.add(extra)
    db.session.flush()
    db.session.add(Inscripcion(campeonato_id=camp.id, competidor_id=extra.id,
                               modalidades=["COMBATE"], estado="aceptada"))
    db.session.commit()
    assert Inscripcion.query.count() == 3

    resp = _importar(app, token, paquete, modo="reemplazar")

    assert resp.status_code == 200
    assert Inscripcion.query.count() == 2
    # El competidor sigue registrado: reemplazar solo toca el campeonato.
    assert Competidor.query.filter_by(nombre_completo="Extra Local").count() == 1


def test_reemplazar_tampoco_borra_una_llave_ya_disputada(destino, paquete):
    """La invariante dura: ninguna importación destruye resultados."""
    app, token = destino
    _importar(app, token, paquete)

    from app.models.llave import Llave

    llave = Llave.query.one()
    llave.estado = "terminada"
    llave.estructura = {"competidores": [{"nombre": "Ana Ruiz"}], "campeon": "Ana Ruiz"}
    db.session.commit()

    resp = _importar(app, token, paquete, modo="reemplazar", forzar=1)

    assert resp.status_code == 200
    conservada = Llave.query.one()
    assert conservada.estado == "terminada"
    assert conservada.estructura["campeon"] == "Ana Ruiz"


def test_un_paquete_ajeno_se_rechaza(destino):
    app, token = destino
    resp = _importar(app, token, {"formato": "otra-cosa", "datos": []})

    assert resp.status_code == 400
    assert "paquete de DINAMYT" in resp.get_json()["error"]

    from app.models.campeonato import Campeonato
    assert Campeonato.query.count() == 0


def test_el_paquete_de_usuarios_va_por_su_cuenta(tmp_path, destino):
    """Exportar/importar solo usuarios, para preparar la otra instancia."""
    origen = _app(tmp_path / "origen3.db")
    ctx = origen.app_context()
    ctx.push()
    db.create_all()
    admin = _crear_admin()
    _sembrar_origen(admin)
    resp = origen.test_client().get(
        "/api/sincronizacion/usuarios/exportar",
        headers={"Authorization": f"Bearer {_token(admin)}"},
    )
    datos = resp.get_json()
    db.session.remove()
    ctx.pop()

    assert datos["formato"] == "dinamyt-usuarios"
    assert len(datos["usuarios"]) == 2

    app, token = destino
    resp = _importar(app, token, datos)

    assert resp.status_code == 200
    from app.models.usuario import Usuario
    assert Usuario.query.filter(Usuario.rol != "admin").count() == 2


# ── La identidad del ecosistema viaja en el paquete (F6) ────────────────
#
# `eco_sub` es el «quién eres» que firma el portal. Sin él, cada paquete que se
# importa deja cuentas sin enlazar: ni les llega el tema y el idioma de su
# cuenta, ni la vuelta de los resultados sabe a quién corresponden.

SUB_JUEZ = "11111111-1111-4111-8111-111111111111"
SUB_MAESTRO = "22222222-2222-4222-8222-222222222222"
SUB_AJENO = "33333333-3333-4333-8333-333333333333"


def _con_identidades(paquete):
    """El mismo paquete, pero con la identidad puesta en cada usuario."""
    subs = {"juez@test.local": SUB_JUEZ, "maestro@test.local": SUB_MAESTRO}
    for u in paquete["usuarios"]:
        u["eco_sub"] = subs[u["email"]]
    return paquete


def test_el_paquete_reserva_sitio_para_la_identidad(paquete):
    """Aunque el origen no tenga ninguna, la clave viaja y la versión sube."""
    assert paquete["version"] == 2
    assert all("eco_sub" in u for u in paquete["usuarios"])


def test_la_identidad_se_enlaza_al_importar(destino, paquete):
    app, token = destino
    resp = _importar(app, token, _con_identidades(paquete))

    assert resp.status_code == 200
    assert resp.get_json()["identidades"] == {"enlazadas": 2, "omitidas": 0}

    from app.models.usuario import Usuario
    assert Usuario.query.filter_by(email="juez@test.local").one().eco_sub == SUB_JUEZ
    assert Usuario.query.filter_by(email="maestro@test.local").one().eco_sub == SUB_MAESTRO


def test_no_pisa_una_identidad_que_ya_estaba(destino, paquete):
    """No se elige por el importador cuál de las dos cuentas es la buena.

    Misma prudencia que `resolver_espejo` con `correo_ocupado`: se para, se
    deja lo local, y que lo mire una persona. Aquí el enlace decide además de
    quién son los resultados que suben después del evento.
    """
    app, token = destino
    from app.models.usuario import Usuario

    previo = Usuario(email="juez@test.local", nombre="Juez Local", rol="juez",
                     activo=True, eco_sub=SUB_AJENO)
    previo.set_password("secret123")
    db.session.add(previo)
    db.session.commit()

    resp = _importar(app, token, _con_identidades(paquete))
    cuerpo = resp.get_json()

    assert resp.status_code == 200
    assert cuerpo["identidades"] == {"enlazadas": 1, "omitidas": 1}
    assert any("otra cuenta del ecosistema" in a for a in cuerpo["avisos"])
    # El enlace local sobrevive: el del paquete no se aplicó.
    assert Usuario.query.filter_by(email="juez@test.local").one().eco_sub == SUB_AJENO


def test_dos_filas_no_pueden_ser_la_misma_cuenta(destino, paquete):
    """El juez ya estaba aquí (mismo uid), pero su cuenta la tiene otra fila.

    Pasa cuando alguien entró desde el portal con esa cuenta en la instalación
    de destino y quedó en OTRA fila. Enlazar las dos sería decir que son la
    misma persona: no se hace, se avisa.
    """
    app, token = destino
    from app.models.usuario import Usuario

    uid_juez = next(u["uid"] for u in paquete["usuarios"] if u["email"] == "juez@test.local")
    mismo = Usuario(email="juez@test.local", nombre="Juez Uno", rol="juez",
                    activo=True, uid=uid_juez)
    mismo.set_password("secret123")
    otro = Usuario(email="otro@test.local", nombre="Otro", rol="juez",
                   activo=True, eco_sub=SUB_JUEZ)
    otro.set_password("secret123")
    db.session.add_all([mismo, otro])
    db.session.commit()

    resp = _importar(app, token, _con_identidades(paquete))
    cuerpo = resp.get_json()

    assert cuerpo["identidades"] == {"enlazadas": 1, "omitidas": 1}
    assert any("ya la tiene" in a for a in cuerpo["avisos"])
    assert Usuario.query.filter_by(email="juez@test.local").one().eco_sub is None
    assert Usuario.query.filter_by(email="otro@test.local").one().eco_sub == SUB_JUEZ


def test_la_identidad_manda_sobre_el_correo(destino, paquete):
    """El correo se cambia en el portal; el `sub` no cambia nunca."""
    app, token = destino
    from app.models.usuario import Usuario

    previo = Usuario(email="juez-viejo@test.local", nombre="Juez Local",
                     rol="juez", activo=True, eco_sub=SUB_JUEZ)
    previo.set_password("secret123")
    db.session.add(previo)
    db.session.commit()

    resp = _importar(app, token, _con_identidades(paquete))

    assert resp.status_code == 200
    # No se duplicó: la fila de siempre es la misma persona.
    assert Usuario.query.filter_by(eco_sub=SUB_JUEZ).count() == 1


def test_un_paquete_de_la_version_anterior_se_importa_igual(destino, paquete):
    """El 9 de octubre el paquete que haya es el que hay."""
    paquete["version"] = 1
    for u in paquete["usuarios"]:
        u.pop("eco_sub", None)

    app, token = destino
    resp = _importar(app, token, paquete)

    assert resp.status_code == 200
    assert resp.get_json()["identidades"] == {"enlazadas": 0, "omitidas": 0}
    from app.models.usuario import Usuario
    assert Usuario.query.filter(Usuario.rol != "admin").count() == 2
