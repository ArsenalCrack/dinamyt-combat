"""
El pase del ecosistema: verificar aquí el RS256 que firma `ecosystem-api`.

Es el bloque **C1** de §4.2 del plan maestro, y el primer ladrillo de la
identidad única: a partir de aquí Campeonatos puede reconocer a alguien que
inició sesión en DINAMYT sin volver a pedirle la contraseña.

── Qué NO hace ──────────────────────────────────────────────────────────────

No busca al usuario, no lo crea y no decide si puede entrar. Aquí solo se
contesta una pregunta: **¿este token lo firmó el ecosistema y sigue vivo?**
Resolver a quién corresponde (el espejo en `usuarios`) es C3, y decidir qué
puede hacer es C2. Mezclarlas es cómo se acaba con un verificador que además
da de alta gente.

── El modo local sigue siendo el modo local ─────────────────────────────────

Sin `ECOSYSTEM_JWKS_URL`, **esta función no existe**: no hay red que consultar
y todo pase del ecosistema se rechaza, con el login propio de Campeonatos
respondiendo como siempre. Es el mismo criterio que ya aplican Membresías y el
correo del ecosistema, y aquí no es una comodidad: el 9 de octubre, en un
gimnasio sin internet, la app tiene que arrancar y juzgar combates igual.

── Los dos cierres, y por qué el segundo no sobra ───────────────────────────

Se exige el **emisor** y se rechaza cualquier token con `purpose`. La misma
llave RS256 firma las sesiones y los enlaces de invitación del maestro, que
duran siete días y viajan por WhatsApp: sin el primer cierre, uno de esos
enlaces abriría sesión aquí. El segundo está para el día en que alguien añada
otro token firmado con esa llave y se olvide de darle su propio emisor.
Membresías cierra exactamente igual (`lib/auth/tokens.ts`).
"""

import logging
import os
import threading

import jwt
from flask import current_app, has_app_context
from jwt import PyJWKClient

log = logging.getLogger(__name__)

# Quién firma las SESIONES del ecosistema. Los enlaces de un solo uso llevan
# `dinamyt-ecosystem-invitacion`, y por eso no valen aquí.
EMISOR_ECOSYSTEM = "dinamyt-ecosystem"

# El scope que habilita ESTA app. Lo llena el plan contratado por el club —o
# por su federación, que desde el 29 de agosto se hereda hacia abajo.
SCOPE_CAMPEONATOS = "campeonatos"

# Cuánto se espera al JWKS. El valor por defecto de PyJWKClient son 30 s, y
# aquí eso es una trampa: se descarga DENTRO de una petición y el despliegue
# corre con un solo worker de eventlet, así que un ecosistema caído no daría
# errores sueltos — congelaría la app entera 30 s por petición. Tres segundos
# fallan rápido y dejan el login propio respondiendo.
ESPERA_JWKS_SEG = 3

# Margen de reloj. Dos máquinas distintas nunca van al segundo, y un pase de
# 30 minutos no se debilita por medio minuto.
DESFASE_RELOJ_SEG = 30

# Un cliente por URL: trae dentro la caché de llaves, así que crear uno nuevo
# en cada petición significaría descargar el JWKS en cada petición.
_clientes = {}
_lock = threading.Lock()


def url_jwks():
    """La URL del JWKS del ecosistema, o cadena vacía si no hay ecosistema."""
    if has_app_context():
        crudo = current_app.config.get("ECOSYSTEM_JWKS_URL")
    else:
        crudo = os.getenv("ECOSYSTEM_JWKS_URL")
    return (crudo or "").strip()


def hay_ecosistema():
    """`True` si esta instalación habla con el ecosistema."""
    return bool(url_jwks())


def _cliente_jwks(url):
    """El cliente de JWKS de esa URL, creado una sola vez."""
    with _lock:
        cliente = _clientes.get(url)
        if cliente is None:
            cliente = PyJWKClient(url, cache_keys=True, timeout=ESPERA_JWKS_SEG)
            _clientes[url] = cliente
        return cliente


def olvidar_clientes():
    """Vacía la caché de clientes. Para las pruebas y para un cambio de URL en
    caliente: sin esto, la instalación seguiría preguntando al JWKS viejo."""
    with _lock:
        _clientes.clear()


def verificar_pase(token):
    """
    Los claims del pase si lo firmó el ecosistema y sigue vivo; `None` si no.

    **Falla cerrado y en silencio hacia fuera**: cualquier problema —firma
    mala, expirado, emisor ajeno, JWKS inalcanzable— devuelve `None` y queda
    en el registro. Quien llama decide qué contarle a la persona, y nunca se
    le cuenta cuál de los motivos fue: eso es un mapa para adivinar tokens.
    """
    if not token:
        return None

    url = url_jwks()
    if not url:
        # Modo local: no hay a quién preguntar, y no es un error.
        return None

    try:
        llave = _cliente_jwks(url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            llave.key,
            algorithms=["RS256"],
            issuer=EMISOR_ECOSYSTEM,
            leeway=DESFASE_RELOJ_SEG,
        )
    except Exception as exc:  # noqa: BLE001 — aquí TODO fallo es «no pasa»
        log.warning("[ecosistema] pase rechazado: %s: %s", type(exc).__name__, exc)
        return None

    if claims.get("purpose"):
        log.warning(
            "[ecosistema] pase rechazado: es un token de un solo uso (%s), no una sesión.",
            claims.get("purpose"),
        )
        return None

    return claims


def abre_campeonatos(claims):
    """
    `True` si el plan de esa persona incluye Campeonatos.

    Va aparte de `verificar_pase` a propósito: una cosa es **quién eres** —la
    firma— y otra **qué abres** —lo que se paga—. El pase de alguien cuyo club
    no tiene plan es perfectamente válido; lo que no tiene es esta app.
    """
    if not claims:
        return False
    scopes = claims.get("app_scopes") or []
    return SCOPE_CAMPEONATOS in scopes
