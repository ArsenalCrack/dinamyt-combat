"""
El pase del ecosistema (C1): qué entra y, sobre todo, qué NO entra.

Lo que se prueba aquí es la puerta de la identidad única. Si se abre de más,
cualquiera con un enlace de invitación reenviado por WhatsApp entra a
Campeonatos como el maestro al que se lo mandaron; si se abre de menos, el día
del campeonato nadie entra. Las dos cosas se descubren tarde.
"""

import base64
import hashlib
import hmac
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app import identidad


LLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _LlaveFirmante:
    """Lo que devuelve PyJWKClient: un objeto con la llave pública dentro."""

    key = LLAVE.public_key()


class _ClienteDeMentira:
    """Un JWKS que no viaja por la red. Cuenta cuántas veces le preguntan."""

    consultas = 0

    def get_signing_key_from_jwt(self, token):
        _ClienteDeMentira.consultas += 1
        return _LlaveFirmante()


@pytest.fixture(autouse=True)
def _sin_red(monkeypatch):
    """Ningún test toca la red, y el JWKS empieza configurado."""
    _ClienteDeMentira.consultas = 0
    identidad.olvidar_clientes()
    monkeypatch.setenv("ECOSYSTEM_JWKS_URL", "https://ejemplo.invalid/auth/jwks")
    monkeypatch.setattr(identidad, "_cliente_jwks", lambda url: _ClienteDeMentira())
    yield
    identidad.olvidar_clientes()


def _b64(dato):
    """Un trozo de JWT: JSON compacto en base64url sin relleno."""
    crudo = json.dumps(dato, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(crudo).rstrip(b"=")


def pase(**extra):
    """Un pase del ecosistema, firmado como lo firma él."""
    ahora = int(time.time())
    cuerpo = {
        "sub": "6c1e1b3e-0000-4000-8000-000000000001",
        "email": "maestro@dinamyt.org",
        "iss": identidad.EMISOR_ECOSYSTEM,
        "iat": ahora,
        "exp": ahora + 1800,
        "app_scopes": ["campeonatos"],
        "role_campeonatos": "maestro",
    }
    cuerpo.update(extra)
    return jwt.encode(cuerpo, LLAVE, algorithm="RS256")


def test_un_pase_del_ecosistema_entra():
    claims = identidad.verificar_pase(pase())
    assert claims is not None
    assert claims["email"] == "maestro@dinamyt.org"
    assert identidad.abre_campeonatos(claims) is True


def test_sin_jwks_no_hay_ecosistema_y_no_se_consulta_nada(monkeypatch):
    # El modo local del día del campeonato: sin internet no hay a quién
    # preguntar. Lo importante no es solo que devuelva None, es que NO SALGA
    # a la red — si lo intentara, cada petición esperaría al tiempo de espera
    # con el gimnasio sin conexión.
    monkeypatch.setenv("ECOSYSTEM_JWKS_URL", "")
    assert identidad.hay_ecosistema() is False
    assert identidad.verificar_pase(pase()) is None
    assert _ClienteDeMentira.consultas == 0


def test_un_enlace_de_invitacion_no_es_una_sesion():
    # Misma llave, otro emisor: dura siete días y viaja por WhatsApp.
    invitacion = pase(iss="dinamyt-ecosystem-invitacion", purpose="set-password")
    assert identidad.verificar_pase(invitacion) is None


def test_un_token_de_un_solo_uso_con_el_emisor_bueno_tampoco():
    # El segundo cierre: para el día en que alguien firme otra cosa con esta
    # llave y se olvide de darle su propio emisor.
    assert identidad.verificar_pase(pase(purpose="reset-password")) is None


def test_un_pase_vencido_no_entra():
    ahora = int(time.time())
    assert identidad.verificar_pase(pase(iat=ahora - 7200, exp=ahora - 3600)) is None


def test_no_se_acepta_otro_algoritmo_con_la_llave_publica():
    # La confusión de algoritmos: firmar HS256 usando como secreto la llave
    # PÚBLICA, que es pública. Solo se cierra fijando los algoritmos.
    publica = LLAVE.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    # Se arma a mano: PyJWT se niega a FIRMAR HS256 con una llave asimétrica,
    # y quien ataque no va a usar PyJWT. Lo que hay que probar es que aquí se
    # rechaza al verificar, que es el único lado que controlamos.
    ahora = int(time.time())
    cabecera = _b64({"alg": "HS256", "typ": "JWT"})
    cuerpo = _b64(
        {
            "sub": "intruso",
            "iss": identidad.EMISOR_ECOSYSTEM,
            "exp": ahora + 1800,
            "app_scopes": ["campeonatos"],
        }
    )
    firmado = cabecera + b"." + cuerpo
    firma = base64.urlsafe_b64encode(
        hmac.new(publica, firmado, hashlib.sha256).digest()
    ).rstrip(b"=")
    falso = (firmado + b"." + firma).decode()

    assert identidad.verificar_pase(falso) is None


def test_un_jwks_caido_rechaza_en_vez_de_reventar(monkeypatch):
    def explota(url):
        raise RuntimeError("no hay red")

    monkeypatch.setattr(identidad, "_cliente_jwks", explota)
    # Falla cerrado: no entra nadie, pero tampoco se cae la petición — el
    # login propio de Campeonatos sigue contestando.
    assert identidad.verificar_pase(pase()) is None


def test_sin_token_no_se_pregunta_nada():
    assert identidad.verificar_pase(None) is None
    assert identidad.verificar_pase("") is None
    assert _ClienteDeMentira.consultas == 0


def test_el_plan_decide_que_abre_no_la_firma():
    # Un pase perfectamente válido de alguien cuyo club no tiene plan: es
    # quien dice ser, y no abre esta app.
    claims = identidad.verificar_pase(pase(app_scopes=["membresias"]))
    assert claims is not None
    assert identidad.abre_campeonatos(claims) is False
    assert identidad.abre_campeonatos(None) is False
