"""
La publicación en vivo (`app/en_vivo.py`, decisión 9 del plan maestro).

Dos instalaciones de verdad en el mismo proceso —la de INTERNET y la del
EVENTO, cada una con su base—, como en `test_subida_resultados.py`: el paquete
viaja de una a otra por sus rutas, y el PC del evento publica hablando con el
cliente de pruebas de internet, no con un simulacro.

Lo que se defiende:

  1. **La llave viaja solo con la sede cedida**: el paquete «para el evento» la
     lleva; una copia de prueba no. Y la de la víspera y la de la mañana son la
     misma.
  2. **El PC la guarda al importar y publica**: el público ve los resultados
     con la hora del dato, y lo que no cambió no se vuelve a mandar.
  3. **La llave solo abre lo suyo**: una falsa, la de otro campeonato, una
     caducada, una retirada o la de un campeonato devuelto a la nube, 401. Y el
     nombre que se enseña es el de internet, no el del archivo.
  4. **Lo viejo no pisa lo nuevo.**
  5. **F8 y la publicación no se pisan**: mientras se publica en vivo, la cola
     de F8 no lo cuenta; cuando la llave deja de valer, F8 vuelve a encargarse.
"""

import io
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import cartero, create_app, en_vivo  # noqa: E402
from app.config import DevelopmentConfig  # noqa: E402
from app.extensions import db  # noqa: E402

INTERNET = "https://campeonatos.ejemplo.invalid"


def _app():
    DevelopmentConfig.SQLALCHEMY_DATABASE_URI = "sqlite://"
    return create_app("development")


def _token(user):
    from flask_jwt_extended import create_access_token

    return create_access_token(identity=str(user.id))


def _usuario(email, rol, **extra):
    from app.models.usuario import Usuario

    u = Usuario(email=email, nombre=email.split("@")[0].upper(), rol=rol,
                activo=True, **extra)
    u.set_password("secret123")
    db.session.add(u)
    db.session.commit()
    return u


class Mundo:
    pass


@pytest.fixture()
def mundo(monkeypatch):
    monkeypatch.setenv("CAMPEONATOS_ONLINE_URL", INTERNET)
    en_vivo._estado.clear()

    m = Mundo()
    m.internet = _app()
    m.evento = _app()
    m.cliente_internet = m.internet.test_client()
    m.cliente_evento = m.evento.test_client()

    # ── En internet: el campeonato, su dueño, un maestro y otro campeonato ──
    with m.internet.app_context():
        from app.models.campeonato import Campeonato
        from app.models.tatami import Tatami

        db.create_all()
        admin = _usuario("admin@fede.org", "admin")
        maestro = _usuario("maestro@t.org", "maestro", creado_por_id=admin.id)
        camp = Campeonato(nombre="COPA NACIONAL", estado="preparacion", activo=True,
                          created_by=admin.id)
        otro = Campeonato(nombre="OTRA COPA", estado="preparacion", activo=True,
                          created_by=admin.id)
        db.session.add_all([camp, otro])
        db.session.commit()
        db.session.add(Tatami(numero=1, campeonato_id=camp.id))
        db.session.commit()
        m.camp_id, m.otro_id = camp.id, otro.id
        m.t_admin, m.t_maestro = _token(admin), _token(maestro)

    def transporte(metodo, url, cabeceras, cuerpo=None, **_):
        assert url.startswith(INTERNET)
        ruta = url[len(INTERNET):]
        m.enviados.append(ruta)
        r = m.cliente_internet.open(ruta, method=metodo, headers=cabeceras, json=cuerpo)
        return r.status_code, list(r.headers.items()), r.get_json() or {}

    m.enviados = []
    monkeypatch.setattr(cartero, "_enviar_http", transporte)

    with m.evento.app_context():
        db.create_all()
        m.t_local = _token(_usuario("local@fede.org", "admin"))
        yield m
        db.session.remove()
        db.drop_all()
    with m.internet.app_context():
        db.drop_all()
    en_vivo._estado.clear()


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _bajar(m, para_el_evento=True, camp_id=None):
    ruta = f"/api/sincronizacion/campeonato/{camp_id or m.camp_id}/exportar"
    if para_el_evento:
        ruta += "?para_el_evento=1"
    r = m.cliente_internet.get(ruta, headers=_h(m.t_admin))
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _importar_en_el_evento(m, paquete):
    datos = {"file": (io.BytesIO(json.dumps(paquete).encode()), "paquete.json")}
    r = m.cliente_evento.post("/api/sincronizacion/importar", data=datos,
                              headers=_h(m.t_local), content_type="multipart/form-data")
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def _camp_local(m):
    from app.models.campeonato import Campeonato

    return Campeonato.query.filter(Campeonato.publicar_llave.isnot(None)).first() \
        or Campeonato.query.first()


def _competir(m, nombre="COMBATE -60KG", competidores=("ANA", "LUIS", "MIA")):
    """Un podio en el PC del evento: una llave de combate terminada."""
    from app.api.llaves import generar_estructura, registrar_resultado, siguiente_partido
    from app.models.llave import Llave
    from app.models.tatami import Tatami

    camp = _camp_local(m)
    tatami = Tatami.query.filter_by(campeonato_id=camp.id).first()
    est = generar_estructura([{"nombre": n} for n in competidores])
    while (sig := siguiente_partido(est)) is not None:
        registrar_resultado(est, sig[0], sig[1], 1)
    db.session.add(Llave(campeonato_id=camp.id, tatami_id=tatami.id, tipo="combate",
                         nombre=nombre, estado="terminada", estructura=est))
    db.session.commit()


def _publico(m):
    r = m.cliente_internet.get("/api/resultados/campeonatos")
    return {c["nombre"]: c for c in r.get_json()}


def _evento_listo(m):
    """El recorrido normal: bajar para el evento, importar, competir."""
    paquete = _bajar(m)
    _importar_en_el_evento(m, paquete)
    _competir(m)
    return paquete


# ══════════════════════════════════════════════════════════════════════════
#  1 · La llave viaja solo con la sede cedida
# ══════════════════════════════════════════════════════════════════════════

def test_el_paquete_para_el_evento_lleva_la_llave_y_una_copia_de_prueba_no(mundo):
    m = mundo
    copia = _bajar(m, para_el_evento=False)
    assert "publicacion" not in copia

    paquete = _bajar(m)
    pub = paquete["publicacion"]
    assert pub["llave"] and pub["export_uuid"] == paquete["campeonato"]["uid"]
    hasta = datetime.fromisoformat(pub["hasta"])
    assert hasta > datetime.now(timezone.utc) + timedelta(days=3)
    assert paquete["version"] >= 8


def test_la_bajada_de_la_vispera_y_la_de_la_manana_llevan_la_misma_llave(mundo):
    m = mundo
    vispera = _bajar(m)["publicacion"]["llave"]
    # Ya cedido, la de la mañana se baja sin marcar: lleva la misma llave.
    manana = _bajar(m, para_el_evento=False)["publicacion"]["llave"]
    assert vispera == manana


def test_la_llave_no_sale_en_la_ficha_del_campeonato(mundo):
    m = mundo
    llave = _bajar(m)["publicacion"]["llave"]
    r = m.cliente_internet.get(f"/api/campeonatos/{m.camp_id}", headers=_h(m.t_admin))
    assert llave not in json.dumps(r.get_json())
    assert r.get_json()["publicar_hasta"]


# ══════════════════════════════════════════════════════════════════════════
#  2 · El PC la guarda y publica
# ══════════════════════════════════════════════════════════════════════════

def test_el_pc_guarda_la_llave_al_importar_y_lo_avisa(mundo):
    m = mundo
    informe = _importar_en_el_evento(m, _bajar(m))
    assert any("en vivo" in a for a in informe["avisos"])
    camp = _camp_local(m)
    assert camp.publicar_llave and camp.publicar_hasta
    # La copia del evento nace sin candado: allí se escribe.
    assert camp.sede_local_desde is None


def test_el_pc_publica_y_el_publico_ve_la_hora_del_dato(mundo):
    m = mundo
    _evento_listo(m)

    estado = en_vivo.publicar()
    assert m.enviados == ["/api/resultados/en-vivo"]
    assert estado[0]["ultimo_envio_at"] and not estado[0]["ultimo_error"]

    fila = _publico(m)["COPA NACIONAL"]
    assert fila["publicado"] is True and fila["en_vivo"] is True
    assert fila["num_resultados"] == 1 and fila["datos_de"]

    # El enlace al id del campeonato de internet enseña lo que llegó, sin uids.
    r = m.cliente_internet.get(f"/api/resultados/campeonato/{m.camp_id}").get_json()
    assert r["en_vivo"] is True and r["datos_de"]
    assert "competidor_uid" not in json.dumps(r["resultados"])


def test_lo_que_no_cambio_no_se_vuelve_a_mandar_y_lo_nuevo_si(mundo):
    m = mundo
    _evento_listo(m)
    en_vivo.publicar()
    en_vivo.publicar()
    assert len(m.enviados) == 1, "sin cambios no se manda nada"

    _competir(m, nombre="COMBATE -70KG", competidores=("JUAN", "PEDRO"))
    en_vivo.publicar()
    assert len(m.enviados) == 2
    assert _publico(m)["COPA NACIONAL"]["num_resultados"] == 2


def test_sin_resultados_todavia_no_se_manda_nada(mundo):
    m = mundo
    _importar_en_el_evento(m, _bajar(m))
    en_vivo.publicar()
    assert m.enviados == []


def test_sin_destino_no_se_publica_y_el_informe_lo_dice(mundo, monkeypatch):
    m = mundo
    monkeypatch.delenv("CAMPEONATOS_ONLINE_URL")
    informe = _importar_en_el_evento(m, _bajar(m))
    assert any("CAMPEONATOS_ONLINE_URL" in a for a in informe["avisos"])
    _competir(m)
    en_vivo.publicar()
    assert m.enviados == []


# ══════════════════════════════════════════════════════════════════════════
#  3 · La llave solo abre lo suyo
# ══════════════════════════════════════════════════════════════════════════

def _sobre_local(m):
    from app.api.resultados import sobre_de_resultados

    return sobre_de_resultados(_camp_local(m))


def _mandar(m, llave, sobre):
    return m.cliente_internet.post("/api/resultados/en-vivo", json=sobre,
                                   headers={en_vivo.CABECERA: llave})


def test_una_llave_falsa_no_publica(mundo):
    m = mundo
    _evento_listo(m)
    r = _mandar(m, "llave-inventada", _sobre_local(m))
    assert r.status_code == 401
    assert r.get_json()["motivo"] == "llave"
    # Sin cabecera ni se lee el cuerpo.
    r = m.cliente_internet.post("/api/resultados/en-vivo", json=_sobre_local(m))
    assert r.status_code == 401
    assert _publico(m)["COPA NACIONAL"]["publicado"] is False


def test_la_llave_de_un_campeonato_no_publica_en_otro(mundo):
    m = mundo
    _evento_listo(m)
    llave_otro = _bajar(m, camp_id=m.otro_id)["publicacion"]["llave"]
    r = _mandar(m, llave_otro, _sobre_local(m))
    assert r.status_code == 401


def test_el_nombre_que_se_ensena_es_el_de_internet(mundo):
    m = mundo
    _evento_listo(m)
    sobre = _sobre_local(m)
    sobre["campeonato"]["nombre"] = "CAMPEONATO FALSO"
    assert _mandar(m, _camp_local(m).publicar_llave, sobre).status_code == 200
    assert _publico(m)["COPA NACIONAL"]["publicado"] is True
    assert "CAMPEONATO FALSO" not in _publico(m)


def test_devolverlo_a_la_nube_retira_la_llave_y_f8_vuelve_a_encargarse(mundo):
    m = mundo
    _evento_listo(m)
    en_vivo.publicar()
    r = m.cliente_internet.post(f"/api/campeonatos/{m.camp_id}/sede", json={"sede": "nube"},
                                headers=_h(m.t_admin))
    assert r.status_code == 200

    _competir(m, nombre="COMBATE -70KG", competidores=("JUAN", "PEDRO"))
    estado = en_vivo.publicar()
    assert estado[0]["rechazada"] is True and estado[0]["activa"] is False
    # Y la cola de F8 vuelve a contarlo: se sube al final con la sesión del admin.
    assert [p["nombre"] for p in cartero.estado()["pendientes"]] == ["COPA NACIONAL"]
    # Rechazada, no se insiste en cada vuelta.
    enviados = len(m.enviados)
    en_vivo.publicar()
    assert len(m.enviados) == enviados


def test_retirar_la_llave_desde_internet(mundo):
    m = mundo
    _evento_listo(m)
    ruta = f"/api/campeonatos/{m.camp_id}/llave-publicacion"
    assert m.cliente_internet.delete(ruta, headers=_h(m.t_maestro)).status_code == 403
    r = m.cliente_internet.delete(ruta, headers=_h(m.t_admin))
    assert r.status_code == 200
    # Sigue cedido: solo se retira la llave.
    assert r.get_json()["campeonato"]["sede"] == "local"
    assert r.get_json()["campeonato"]["publicar_hasta"] is None
    assert _mandar(m, _camp_local(m).publicar_llave, _sobre_local(m)).status_code == 401

    # Una bajada nueva entrega OTRA llave, y la vieja sigue muerta.
    nueva = _bajar(m, para_el_evento=False)["publicacion"]["llave"]
    assert nueva != _camp_local(m).publicar_llave
    assert _mandar(m, _camp_local(m).publicar_llave, _sobre_local(m)).status_code == 401
    assert _mandar(m, nueva, _sobre_local(m)).status_code == 200


def test_la_llave_caduca(mundo):
    m = mundo
    _evento_listo(m)
    with m.internet.app_context():
        from app.models.campeonato import Campeonato

        camp = db.session.get(Campeonato, m.camp_id)
        camp.publicar_hasta = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
        db.session.commit()
    assert _mandar(m, _camp_local(m).publicar_llave, _sobre_local(m)).status_code == 401


# ══════════════════════════════════════════════════════════════════════════
#  4 · Lo viejo no pisa lo nuevo
# ══════════════════════════════════════════════════════════════════════════

def test_una_instantanea_mas_vieja_se_descarta(mundo):
    m = mundo
    _evento_listo(m)
    llave = _camp_local(m).publicar_llave
    vieja = _sobre_local(m)
    vieja["exportado_at"] = "2026-10-10T16:40:00+00:00"
    nueva = _sobre_local(m)
    nueva["exportado_at"] = "2026-10-10T16:45:00+00:00"
    nueva["resultados"] = nueva["resultados"] * 2

    assert _mandar(m, llave, nueva).status_code == 200
    r = _mandar(m, llave, vieja)
    assert r.status_code == 200 and r.get_json()["descartado"] is True
    assert _publico(m)["COPA NACIONAL"]["num_resultados"] == 2


def test_un_reloj_adelantado_no_hace_parecer_nuevo_lo_que_no_es(mundo):
    m = mundo
    _evento_listo(m)
    sobre = _sobre_local(m)
    sobre["exportado_at"] = "2099-01-01T00:00:00+00:00"
    assert _mandar(m, _camp_local(m).publicar_llave, sobre).status_code == 200
    datos_de = datetime.fromisoformat(_publico(m)["COPA NACIONAL"]["datos_de"])
    assert datos_de <= datetime.now(timezone.utc)


# ══════════════════════════════════════════════════════════════════════════
#  5 · F8 y la publicación no se pisan
# ══════════════════════════════════════════════════════════════════════════

def test_mientras_se_publica_en_vivo_f8_no_lo_cuenta_como_pendiente(mundo):
    m = mundo
    _evento_listo(m)
    # Antes de la primera vuelta ya no es «pendiente de subir»: es del hilo.
    assert cartero.estado()["pendientes"] == []
    en_vivo.publicar()
    subidos = cartero.estado()["subidos"]
    assert subidos[0]["enviado_por"] == en_vivo.ENVIADO_POR


def test_la_subida_final_de_f8_actualiza_lo_publicado_en_vivo(mundo):
    """El dueño del campeonato es el dueño de la instantánea: su F8 no choca."""
    m = mundo
    _evento_listo(m)
    en_vivo.publicar()
    sobre = _sobre_local(m)
    r = m.cliente_internet.post("/api/resultados/importar", json=sobre, headers=_h(m.t_admin))
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["nuevo"] is False
