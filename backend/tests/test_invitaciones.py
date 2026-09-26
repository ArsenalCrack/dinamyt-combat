"""
Inscribirse por invitación (F5 de `PLAN-CAMPEONATOS.md`).

El escenario: dos federaciones, cada una con su admin y su campeonato, y tres
maestros —uno «de la casa» (creado por el admin, como antes de todo esto) y
dos que llegan desde el portal, sin `creado_por_id`, con el club del
ecosistema en `org_id`—.

Lo que se defiende:

  1. **La puerta nueva:** el club invitado por `org_id` ve el campeonato e
     inscribe, aunque sea de otro workspace; su ficha y su solicitud viven en
     el workspace del campeonato, que es donde el admin las ve.
  2. **Sin invitación, 403 con una frase** (punto 3 de F5).
  3. **La puerta vieja no se cierra:** el maestro de la casa sigue entrando
     sin invitación (la «migración blanda» del punto 4).
  4. **Retirar cierra la puerta** sin borrar lo ya inscrito.
  5. **Un nombre no es una llave:** la invitación solo por nombre no deja
     entrar a nadie de fuera del workspace.
  6. **La misma alumna en dos federaciones:** una ficha en cada una, porque el
     documento es único por workspace.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

from app import create_app, espejo  # noqa: E402
from app.config import DevelopmentConfig  # noqa: E402
from app.extensions import db  # noqa: E402

DevelopmentConfig.SQLALCHEMY_DATABASE_URI = "sqlite://"

FEDE_A = "0f000000-0000-4000-8000-0000000000fa"
FEDE_B = "0f000000-0000-4000-8000-0000000000fb"
CLUB_1 = "0c000000-0000-4000-8000-000000000001"
CLUB_2 = "0c000000-0000-4000-8000-000000000002"


def _token(user):
    from flask_jwt_extended import create_access_token

    return create_access_token(identity=str(user.id))


class Mundo:
    pass


@pytest.fixture()
def mundo(monkeypatch):
    # Sin ecosistema por defecto: cada prueba que lo necesite lo pone.
    monkeypatch.setattr(espejo, "buscar_clubes", lambda texto=None, federacion=None: None)
    # Aquí y no solo al importar: otro módulo cambia la URL en la clase.
    DevelopmentConfig.SQLALCHEMY_DATABASE_URI = "sqlite://"
    app = create_app("development")
    with app.app_context():
        db.create_all()
        from app.models.campeonato import Campeonato
        from app.models.usuario import Usuario

        def usuario(email, rol, **extra):
            u = Usuario(email=email, nombre=email.split("@")[0].upper(), rol=rol,
                        activo=True, **extra)
            u.set_password("secret123")
            db.session.add(u)
            db.session.commit()
            return u

        m = Mundo()
        m.admin_a = usuario("a@fede.org", "admin", org_id=FEDE_A, org_nombre="FEDERACIÓN A")
        m.admin_b = usuario("b@fede.org", "admin", org_id=FEDE_B, org_nombre="FEDERACIÓN B")
        m.de_la_casa = usuario("casa@t.org", "maestro", creado_por_id=m.admin_a.id)
        m.de_la_casa.clubes = ["DOJANG SUR"]
        m.del_portal = usuario("portal@t.org", "maestro", org_id=CLUB_1, eco_sub="sub-portal")
        m.del_portal.clubes = ["CLUB UNO"]
        m.otro = usuario("otro@t.org", "maestro", org_id=CLUB_2)
        m.otro.clubes = ["CLUB DOS"]
        db.session.commit()

        m.camp_a = Campeonato(nombre="COPA A", estado="preparacion", activo=True,
                              created_by=m.admin_a.id, org_id=FEDE_A)
        m.camp_b = Campeonato(nombre="COPA B", estado="preparacion", activo=True,
                              created_by=m.admin_b.id, org_id=FEDE_B)
        db.session.add_all([m.camp_a, m.camp_b])
        db.session.commit()

        m.app = app
        m.cliente = app.test_client()
        m.tokens = {
            nombre: _token(getattr(m, nombre))
            for nombre in ("admin_a", "admin_b", "de_la_casa", "del_portal", "otro")
        }
        yield m
        db.session.remove()
        db.drop_all()


def _h(m, quien):
    return {"Authorization": f"Bearer {m.tokens[quien]}"}


def _invitar(m, quien, camp, **cuerpo):
    return m.cliente.post(f"/api/campeonatos/{camp.id}/clubes", json=cuerpo, headers=_h(m, quien))


def _campeonatos(m, quien):
    return m.cliente.get("/api/inscripciones/maestro/campeonatos", headers=_h(m, quien)).get_json()


ALUMNA = {
    "nombre_completo": "ANA GOMEZ PEREZ",
    "fecha_nacimiento": "2012-05-04",
    "genero": "F",
    "documento": "1088123456",
    "grupo_cinturon": "color",
}


def _inscribir(m, quien, camp, club, **extra):
    return m.cliente.post(
        f"/api/inscripciones/maestro/campeonato/{camp.id}",
        json={"competidor": {**ALUMNA, "club": club}, "peso": 40, **extra},
        headers=_h(m, quien),
    )


# ══════════════════════════════════════════════════════════════════════════
#  1 y 2 · La puerta nueva, y el 403 sin ella
# ══════════════════════════════════════════════════════════════════════════

class TestLaInvitacionAbreLaPuerta:
    def test_sin_invitacion_el_maestro_del_portal_no_ve_nada(self, mundo):
        assert _campeonatos(mundo, "del_portal") == []

    def test_sin_invitacion_inscribir_es_un_403_con_frase(self, mundo):
        r = _inscribir(mundo, "del_portal", mundo.camp_a, "CLUB UNO")
        assert r.status_code == 403
        assert "no está invitado" in r.get_json()["error"]

    def test_invitado_lo_ve_y_sabe_quien_organiza(self, mundo):
        assert _invitar(mundo, "admin_a", mundo.camp_a, org_id=CLUB_1, nombre="Club Uno").status_code == 201
        lista = _campeonatos(mundo, "del_portal")
        assert [c["nombre"] for c in lista] == ["COPA A"]
        assert lista[0]["acceso"] == "invitado"
        assert lista[0]["invitacion"] == "invitado"
        assert lista[0]["organiza"] == "FEDERACIÓN A"

    def test_invitado_inscribe_y_todo_queda_donde_el_admin_lo_ve(self, mundo):
        _invitar(mundo, "admin_a", mundo.camp_a, org_id=CLUB_1, nombre="Club Uno")
        r = _inscribir(mundo, "del_portal", mundo.camp_a, "CLUB UNO")
        assert r.status_code == 201, r.get_json()

        from app.models.competidor import Competidor
        from app.models.invitacion import InvitacionClub

        ficha = Competidor.query.filter_by(documento=ALUMNA["documento"]).one()
        # La ficha es del workspace del CAMPEONATO: es ese admin quien acepta.
        assert ficha.created_by == mundo.admin_a.id
        # Participar ES aceptar.
        assert InvitacionClub.query.one().estado == "aceptado"

        del_admin = mundo.cliente.get(
            f"/api/inscripciones/campeonato/{mundo.camp_a.id}", headers=_h(mundo, "admin_a")
        ).get_json()
        assert [i["estado"] for i in del_admin] == ["pendiente"]

    def test_la_invitacion_es_del_club_y_no_de_cualquiera(self, mundo):
        _invitar(mundo, "admin_a", mundo.camp_a, org_id=CLUB_1, nombre="Club Uno")
        assert _campeonatos(mundo, "otro") == []
        assert _inscribir(mundo, "otro", mundo.camp_a, "CLUB DOS").status_code == 403

    def test_un_campeonato_inactivo_no_existe(self, mundo):
        _invitar(mundo, "admin_a", mundo.camp_a, org_id=CLUB_1, nombre="Club Uno")
        mundo.camp_a.activo = False
        db.session.commit()
        assert _inscribir(mundo, "del_portal", mundo.camp_a, "CLUB UNO").status_code == 404


# ══════════════════════════════════════════════════════════════════════════
#  3 · La puerta vieja sigue abierta
# ══════════════════════════════════════════════════════════════════════════

def test_el_maestro_de_la_casa_sigue_entrando_sin_invitacion(mundo):
    lista = _campeonatos(mundo, "de_la_casa")
    assert [(c["nombre"], c["acceso"]) for c in lista] == [("COPA A", "casa")]
    assert _inscribir(mundo, "de_la_casa", mundo.camp_a, "DOJANG SUR").status_code == 201


# ══════════════════════════════════════════════════════════════════════════
#  4 · Retirar
# ══════════════════════════════════════════════════════════════════════════

class TestRetirar:
    def _invitado_con_una_inscripcion(self, m):
        inv = _invitar(m, "admin_a", m.camp_a, org_id=CLUB_1, nombre="Club Uno").get_json()
        ins = _inscribir(m, "del_portal", m.camp_a, "CLUB UNO").get_json()["inscripcion"]
        return inv["invitacion"]["id"], ins["id"]

    def test_cierra_la_puerta_pero_no_borra_lo_inscrito(self, mundo):
        inv_id, _ = self._invitado_con_una_inscripcion(mundo)
        r = mundo.cliente.delete(
            f"/api/campeonatos/{mundo.camp_a.id}/clubes/{inv_id}", headers=_h(mundo, "admin_a")
        )
        assert r.status_code == 200
        assert _campeonatos(mundo, "del_portal") == []
        assert _inscribir(mundo, "del_portal", mundo.camp_a, "CLUB UNO").status_code == 403
        del_admin = mundo.cliente.get(
            f"/api/inscripciones/campeonato/{mundo.camp_a.id}", headers=_h(mundo, "admin_a")
        ).get_json()
        assert len(del_admin) == 1

    def test_una_rechazada_ya_no_se_corrige_si_se_retiro(self, mundo):
        inv_id, ins_id = self._invitado_con_una_inscripcion(mundo)
        mundo.cliente.patch(f"/api/inscripciones/{ins_id}/estado",
                            json={"estado": "rechazada"}, headers=_h(mundo, "admin_a"))
        mundo.cliente.delete(f"/api/campeonatos/{mundo.camp_a.id}/clubes/{inv_id}",
                             headers=_h(mundo, "admin_a"))
        r = mundo.cliente.put(
            f"/api/inscripciones/maestro/{ins_id}",
            json={"competidor": {**ALUMNA, "club": "CLUB UNO"}, "peso": 41},
            headers=_h(mundo, "del_portal"),
        )
        assert r.status_code == 403

    def test_con_la_invitacion_vigente_si_se_corrige(self, mundo):
        _, ins_id = self._invitado_con_una_inscripcion(mundo)
        mundo.cliente.patch(f"/api/inscripciones/{ins_id}/estado",
                            json={"estado": "rechazada", "motivo": "Peso"},
                            headers=_h(mundo, "admin_a"))
        r = mundo.cliente.put(
            f"/api/inscripciones/maestro/{ins_id}",
            json={"competidor": {**ALUMNA, "club": "CLUB UNO"}, "peso": 41},
            headers=_h(mundo, "del_portal"),
        )
        assert r.status_code == 200, r.get_json()

    def test_volver_a_invitar_a_un_retirado_lo_reabre(self, mundo):
        inv_id, _ = self._invitado_con_una_inscripcion(mundo)
        mundo.cliente.delete(f"/api/campeonatos/{mundo.camp_a.id}/clubes/{inv_id}",
                             headers=_h(mundo, "admin_a"))
        r = _invitar(mundo, "admin_a", mundo.camp_a, org_id=CLUB_1, nombre="Club Uno")
        assert r.status_code == 201
        assert r.get_json()["invitacion"]["id"] == inv_id
        assert _campeonatos(mundo, "del_portal")[0]["nombre"] == "COPA A"


# ══════════════════════════════════════════════════════════════════════════
#  5 · Un nombre no es una llave
# ══════════════════════════════════════════════════════════════════════════

def test_la_invitacion_solo_por_nombre_no_deja_entrar_a_nadie_de_fuera(mundo):
    # El admin B le pone a su maestro el nombre del club invitado por A. Si el
    # nombre abriera la puerta, ese maestro entraría al campeonato de A.
    _invitar(mundo, "admin_a", mundo.camp_a, nombre="Club Dos")
    assert _campeonatos(mundo, "otro") == []
    assert _inscribir(mundo, "otro", mundo.camp_a, "CLUB DOS").status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  6 · La misma alumna en dos federaciones
# ══════════════════════════════════════════════════════════════════════════

def test_la_misma_alumna_en_dos_federaciones_tiene_una_ficha_en_cada_una(mundo):
    _invitar(mundo, "admin_a", mundo.camp_a, org_id=CLUB_1, nombre="Club Uno")
    _invitar(mundo, "admin_b", mundo.camp_b, org_id=CLUB_1, nombre="Club Uno")
    assert _inscribir(mundo, "del_portal", mundo.camp_a, "CLUB UNO").status_code == 201
    r = _inscribir(mundo, "del_portal", mundo.camp_b, "CLUB UNO")
    assert r.status_code == 201, r.get_json()

    from app.models.competidor import Competidor

    fichas = Competidor.query.filter_by(documento=ALUMNA["documento"]).all()
    assert sorted(f.created_by for f in fichas) == sorted([mundo.admin_a.id, mundo.admin_b.id])

    # Y sus solicitudes, las dos, en «mis solicitudes».
    mias = mundo.cliente.get("/api/inscripciones/maestro/mias", headers=_h(mundo, "del_portal"))
    assert len(mias.get_json()) == 2


def test_la_segunda_vez_en_la_misma_federacion_reutiliza_la_ficha(mundo):
    _invitar(mundo, "admin_a", mundo.camp_a, org_id=CLUB_1, nombre="Club Uno")
    from app.models.campeonato import Campeonato

    otra = Campeonato(nombre="COPA A2", estado="preparacion", activo=True,
                      created_by=mundo.admin_a.id)
    db.session.add(otra)
    db.session.commit()
    _invitar(mundo, "admin_a", otra, org_id=CLUB_1, nombre="Club Uno")

    assert _inscribir(mundo, "del_portal", mundo.camp_a, "CLUB UNO").status_code == 201
    r = _inscribir(mundo, "del_portal", otra, "CLUB UNO")
    assert r.status_code == 201
    assert r.get_json()["reutilizada"] is True


def test_los_alumnos_de_un_campeonato_invitado_son_los_de_ese_workspace(mundo):
    _invitar(mundo, "admin_a", mundo.camp_a, org_id=CLUB_1, nombre="Club Uno")
    _inscribir(mundo, "del_portal", mundo.camp_a, "CLUB UNO")
    r = mundo.cliente.get(
        f"/api/inscripciones/maestro/alumnos?campeonato_id={mundo.camp_a.id}",
        headers=_h(mundo, "del_portal"),
    )
    assert r.status_code == 200
    alumnos = r.get_json()
    assert [a["nombre_completo"] for a in alumnos] == ["ANA GOMEZ PEREZ"]
    assert alumnos[0]["inscrito"] is True

    # De un campeonato al que no lo invitaron, nada: ni la lista.
    r = mundo.cliente.get(
        f"/api/inscripciones/maestro/alumnos?campeonato_id={mundo.camp_b.id}",
        headers=_h(mundo, "del_portal"),
    )
    assert r.status_code == 403


# ══════════════════════════════════════════════════════════════════════════
#  Las rutas del administrador
# ══════════════════════════════════════════════════════════════════════════

class TestLasRutasDelAdmin:
    def test_invitar_dos_veces_es_un_409(self, mundo):
        _invitar(mundo, "admin_a", mundo.camp_a, org_id=CLUB_1, nombre="Club Uno")
        r = _invitar(mundo, "admin_a", mundo.camp_a, org_id=CLUB_1, nombre="Club Uno")
        assert r.status_code == 409

    def test_sin_nombre_no_se_invita(self, mundo):
        assert _invitar(mundo, "admin_a", mundo.camp_a, org_id=CLUB_1).status_code == 400

    def test_otro_admin_no_toca_las_invitaciones_ajenas(self, mundo):
        assert _invitar(mundo, "admin_b", mundo.camp_a, org_id=CLUB_1, nombre="X").status_code == 404
        r = mundo.cliente.get(f"/api/campeonatos/{mundo.camp_a.id}/clubes", headers=_h(mundo, "admin_b"))
        assert r.status_code == 404

    def test_un_maestro_no_invita(self, mundo):
        r = _invitar(mundo, "de_la_casa", mundo.camp_a, org_id=CLUB_1, nombre="X")
        assert r.status_code == 403

    def test_la_lista_incluye_las_retiradas(self, mundo):
        inv = _invitar(mundo, "admin_a", mundo.camp_a, org_id=CLUB_1, nombre="Club Uno").get_json()
        mundo.cliente.delete(
            f"/api/campeonatos/{mundo.camp_a.id}/clubes/{inv['invitacion']['id']}",
            headers=_h(mundo, "admin_a"),
        )
        lista = mundo.cliente.get(
            f"/api/campeonatos/{mundo.camp_a.id}/clubes", headers=_h(mundo, "admin_a")
        ).get_json()
        assert [(i["club_nombre"], i["estado"]) for i in lista] == [("CLUB UNO", "retirado")]


class TestBuscarClubes:
    def _buscar(self, m, q=""):
        return m.cliente.get(
            f"/api/campeonatos/{m.camp_a.id}/clubes/buscar?q={q}", headers=_h(m, "admin_a")
        ).get_json()

    def test_sin_ecosistema_lo_dice_y_sugiere_los_clubes_que_conoce(self, mundo):
        r = self._buscar(mundo)
        assert r["disponible"] is False
        # Los dojangs de los maestros de SU workspace: el de la casa.
        assert [c["nombre"] for c in r["clubes"]] == ["DOJANG SUR"]

    def test_con_ecosistema_marca_los_ya_invitados(self, mundo, monkeypatch):
        pedidas = []

        def directorio(texto=None, federacion=None):
            pedidas.append((texto, federacion))
            return [
                {"org_id": CLUB_1, "nombre": "CLUB UNO", "ciudad": "Cali", "afiliado": True},
                {"org_id": CLUB_2, "nombre": "CLUB DOS", "ciudad": None, "afiliado": False},
            ]

        monkeypatch.setattr(espejo, "buscar_clubes", directorio)
        _invitar(mundo, "admin_a", mundo.camp_a, org_id=CLUB_1, nombre="Club Uno")
        r = self._buscar(mundo, "club")
        assert r["disponible"] is True
        assert {c["nombre"]: c["ya_invitado"] for c in r["clubes"]} == {
            "CLUB UNO": True, "CLUB DOS": False,
        }
        # Se pregunta con lo que se escribió y la organización del admin.
        assert pedidas == [("club", FEDE_A)]


def test_borrar_el_campeonato_se_lleva_sus_invitaciones(mundo):
    _invitar(mundo, "admin_a", mundo.camp_a, org_id=CLUB_1, nombre="Club Uno")
    r = mundo.cliente.delete(f"/api/campeonatos/{mundo.camp_a.id}", headers=_h(mundo, "admin_a"))
    assert r.status_code == 200

    from app.models.invitacion import InvitacionClub

    assert InvitacionClub.query.count() == 0


# ══════════════════════════════════════════════════════════════════════════
#  «Solo clubes invitados» (punto 3 de lo que quedaba del plan, 25 sep 2026)
# ══════════════════════════════════════════════════════════════════════════

def _solo_invitados(m, quien, camp, valor):
    return m.cliente.put(f"/api/campeonatos/{camp.id}/clubes/solo-invitados",
                         json={"solo_invitados": valor}, headers=_h(m, quien))


class TestSoloInvitados:
    def test_apagado_la_casa_entra_como_siempre(self, mundo):
        assert mundo.camp_a.solo_invitados in (None, False)
        assert _inscribir(mundo, "de_la_casa", mundo.camp_a, "DOJANG SUR").status_code == 201

    def test_encendido_la_casa_sin_invitacion_no_ve_ni_inscribe(self, mundo):
        r = _solo_invitados(mundo, "admin_a", mundo.camp_a, True)
        assert r.status_code == 200, r.get_json()
        assert _campeonatos(mundo, "de_la_casa") == []
        r = _inscribir(mundo, "de_la_casa", mundo.camp_a, "DOJANG SUR")
        assert r.status_code == 403
        assert "no está invitado" in r.get_json()["error"]

    def test_la_invitacion_por_nombre_vale_dentro_de_la_casa(self, mundo):
        _solo_invitados(mundo, "admin_a", mundo.camp_a, True)
        _invitar(mundo, "admin_a", mundo.camp_a, nombre="Dojang Sur")
        assert [c["nombre"] for c in _campeonatos(mundo, "de_la_casa")] == ["COPA A"]
        assert _inscribir(mundo, "de_la_casa", mundo.camp_a, "DOJANG SUR").status_code == 201

        from app.models.invitacion import InvitacionClub

        # Participar ES aceptar, también por esta puerta.
        assert InvitacionClub.query.one().estado == "aceptado"

    def test_el_de_fuera_invitado_sigue_entrando(self, mundo):
        _solo_invitados(mundo, "admin_a", mundo.camp_a, True)
        _invitar(mundo, "admin_a", mundo.camp_a, org_id=CLUB_1, nombre="Club Uno")
        assert _inscribir(mundo, "del_portal", mundo.camp_a, "CLUB UNO").status_code == 201

    def test_solo_el_dueno_lo_cambia_y_solo_con_un_booleano(self, mundo):
        assert _solo_invitados(mundo, "admin_b", mundo.camp_a, True).status_code == 404
        assert _solo_invitados(mundo, "admin_a", mundo.camp_a, "si").status_code == 400
        db.session.expire_all()
        assert not mundo.camp_a.solo_invitados

    def test_lo_ya_inscrito_se_queda(self, mundo):
        assert _inscribir(mundo, "de_la_casa", mundo.camp_a, "DOJANG SUR").status_code == 201
        _solo_invitados(mundo, "admin_a", mundo.camp_a, True)
        from app.models.competidor import Inscripcion

        assert Inscripcion.query.count() == 1


# ══════════════════════════════════════════════════════════════════════════
#  El aviso al club en DINAMYT (punto 3, 25 sep 2026)
# ══════════════════════════════════════════════════════════════════════════

class TestElAvisoAlClub:
    def test_invitar_del_directorio_avisa_y_lo_dice(self, mundo, monkeypatch):
        avisos = []

        def avisar(org_id, campeonato, organiza=None):
            avisos.append((org_id, campeonato, organiza))
            return True

        monkeypatch.setattr(espejo, "avisar_invitacion_a_club", avisar)
        r = _invitar(mundo, "admin_a", mundo.camp_a, org_id=CLUB_1, nombre="Club Uno")

        assert r.status_code == 201
        assert r.get_json()["avisado"] is True
        assert "Se le avisó en DINAMYT" in r.get_json()["message"]
        assert avisos == [(CLUB_1, "COPA A", "FEDERACIÓN A")]

    def test_por_nombre_no_hay_a_quien_avisar(self, mundo, monkeypatch):
        avisos = []
        monkeypatch.setattr(espejo, "avisar_invitacion_a_club",
                            lambda *a, **k: avisos.append(a) or True)
        r = _invitar(mundo, "admin_a", mundo.camp_a, nombre="Dojang Sur")
        assert r.status_code == 201
        assert r.get_json()["avisado"] is False
        assert avisos == []

    def test_si_dinamyt_no_contesta_la_invitacion_queda_igual(self, mundo, monkeypatch):
        monkeypatch.setattr(espejo, "avisar_invitacion_a_club", lambda *a, **k: False)
        r = _invitar(mundo, "admin_a", mundo.camp_a, org_id=CLUB_1, nombre="Club Uno")
        assert r.status_code == 201
        assert r.get_json()["avisado"] is False
        assert "avisó" not in r.get_json()["message"]


def test_el_cliente_del_aviso_manda_club_campeonato_y_organizador(monkeypatch):
    import io
    import json as _json

    app = create_app("development")
    app.config["ECOSYSTEM_JWKS_URL"] = "https://id.ejemplo.invalid/auth/jwks"
    monkeypatch.setenv("ECOSYSTEM_SYNC_SECRET", "secreto")
    enviado = {}

    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen_falso(peticion, timeout=None):
        enviado["url"] = peticion.full_url
        enviado["cuerpo"] = _json.loads(peticion.data)
        enviado["secreto"] = dict(peticion.header_items())["X-dinamyt-sync"]
        return _Resp(b'{"avisado": true}')

    monkeypatch.setattr(espejo, "urlopen", urlopen_falso)
    with app.app_context():
        assert espejo.avisar_invitacion_a_club(CLUB_1, "COPA A", "FEDERACIÓN A") is True

    assert enviado == {
        "url": "https://id.ejemplo.invalid/sync/aviso-campeonato",
        "cuerpo": {"orgId": CLUB_1, "campeonato": "COPA A", "organiza": "FEDERACIÓN A"},
        "secreto": "secreto",
    }

    def cae(peticion, timeout=None):
        raise OSError("sin red")

    monkeypatch.setattr(espejo, "urlopen", cae)
    with app.app_context():
        assert espejo.avisar_invitacion_a_club(CLUB_1, "COPA A") is False
