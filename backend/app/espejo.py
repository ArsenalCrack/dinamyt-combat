"""
El espejo local de una cuenta del ecosistema (bloque **C3** de §4.2).

`usuarios` deja de ser una tabla de cuentas y pasa a ser un **espejo**: la
cuenta vive en `ecosystem.users` y aquí solo queda la fila que necesitan las
diez claves foráneas y el aislamiento por workspace. Se conserva el `id`
Integer —y con él las FK y el RLS enteros— y se añade `eco_sub`, que es el
`sub` del pase.

── Las tres situaciones, y por qué el correo sigue haciendo falta ───────────

1. **Ya tiene espejo** (`eco_sub` coincide): se usa. Es el caso normal.
2. **Existe con ese correo pero sin `eco_sub`**: se ENLAZA. Es toda la gente
   que ya estaba en Campeonatos antes de la identidad única — la misma
   operación que hizo el guion de reconciliación, pero de a uno y cuando la
   persona entra.
3. **No existe**: se crea, **si el pase trae algún papel de esta app** —uno
   que opere, o competir—.

── El alumno entra, y la fila nace cuando ENTRA (F3) ────────────────────────

Hasta F3 el pase de un alumno no creaba ninguna fila: Campeonatos era solo una
consola de operación y no tenía una pantalla para él. Ahora la tiene
(`/mi-panel`), así que `competitor` y `student` crean el espejo con el papel
`competidor` de principal.

La razón vieja sigue en pie y se sigue cumpliendo: que una federación con
doscientos alumnos no llene esta tabla de gente que no va a entrar nunca. Por
eso la fila nace **aquí, al canjear el pase** —la primera vez que la persona
abre Campeonatos— y no al firmarlo. Quien nunca entra sigue sin existir, y en
`/admin` los competidores quedan detrás de un contador.

`sin_consola` no desaparece: es la respuesta para un pase que no trae NINGÚN
papel de Campeonatos.

── El rol local manda sobre el del pase ─────────────────────────────────────

El pase dice qué rol tiene la persona en su club; la fila local dice qué es en
ESTA aplicación, y puede haber sido puesto a mano por el administrador. Al
crear el espejo se toma el del pase, porque no hay otra cosa; a partir de ahí
manda el local. Es el mismo criterio que Academy, y evita que un cambio de rol
en el portal degrade en silencio al administrador de un campeonato en marcha.

`es_superadmin` **nunca** viaja en este camino: se concede a mano, mirando.
"""

import json
import os
import logging
import secrets
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .extensions import db
from .identidad import url_api_ecosistema
from .models.usuario import ROLES_VALIDOS, Usuario, ordenar_papeles
from .organizacion import (
    ORG_NOMBRE_MAX,
    org_del_pase,
    rellenar_org_de_campeonatos,
    sin_admin_si_ya_hay_otro,
)

log = logging.getLogger(__name__)

# Del catálogo del ecosistema al de aquí. Los que faltan —`guardian`,
# `member`— no tienen nada que hacer en Campeonatos. (`member` llega ya
# traducido a `competitor` desde F1: el portal lo convierte al firmar.)
ROL_DESDE_ECOSISTEMA = {
    "admin": "admin",
    "maestro": "maestro",
    # En el ecosistema, el `coach` del club es quien inscribe a los suyos: eso
    # aquí se llama maestro.
    "coach": "maestro",
    "judge": "juez",
    "juez": "juez",
    # Competir no abre la CONSOLA, pero sí Campeonatos: entra a su panel (F3).
    "competitor": "competidor",
    "student": "competidor",
}

# Tope de la columna `nombre`.
NOMBRE_MAX = 150

# Cuánto se espera al ecosistema para preguntarle por el club. Va DENTRO del
# canje de la sesión, así que si el ecosistema tarda, lo que tarda es entrar.
# Dos segundos y se sigue sin club, que es como se entraba hasta ayer.
ESPERA_CLUB_SEG = 2

# Los roles a los que el club les sirve de algo. Un juez puntúa donde lo
# asignen: no inscribe a nadie y su club no pinta nada.
ROLES_CON_CLUB = ("maestro",)


def es_super(claims):
    """`True` si el pase es de un super-administrador del ecosistema.

    Manda sobre el plan y sobre el rol —quien administra la plataforma no
    pertenece a ningún club y su pase no trae scopes—, pero **no concede
    `es_superadmin` aquí**: el espejo nace como `admin` y el mando de esta app
    se sigue dando a mano, mirando (regla §1.5 de OPERAR).
    """
    return bool((claims or {}).get("is_super_admin"))


def papeles_del_pase(claims):
    """Todos los papeles que trae el pase, ya traducidos a los de aquí.

    Lee `roles_campeonatos` (la lista, F1 del plan) y, si no viene, cae a
    `role_campeonatos`: un ecosistema sin actualizar tiene que seguir dejando
    entrar a la gente exactamente como hasta ahora.
    """
    if not claims:
        return []
    crudos = claims.get("roles_campeonatos")
    if not isinstance(crudos, list):
        crudos = [claims.get("role_campeonatos")]
    return ordenar_papeles(
        ROL_DESDE_ECOSISTEMA.get(str(valor or "").strip()) for valor in crudos
    )


def roles_operativos(claims):
    """Los papeles del pase que abren la consola (sin `competidor`)."""
    return [p for p in papeles_del_pase(claims) if p in ROLES_VALIDOS]


def rol_operativo(claims):
    """El rol principal que tendría en Campeonatos, o `None` si no opera nada."""
    operativos = roles_operativos(claims)
    if operativos:
        return operativos[0]
    # El super-admin entra a administrar aunque no sea miembro de ningún club.
    return "admin" if es_super(claims) else None


def rol_principal(claims):
    """El papel con el que NACE la fila, o `None` si el pase no trae ninguno.

    El que opera, si hay alguno; si no, `competidor` (F3): quien solo compite
    entra a su panel. `None` es el `sin_consola` de siempre.
    """
    rol = rol_operativo(claims)
    if rol:
        return rol
    return "competidor" if "competidor" in papeles_del_pase(claims) else None


def _sumar_papeles_del_pase(usuario, claims):
    """
    Le añade a una fila que YA existía los papeles nuevos que trae su pase.

    Devuelve True si cambió algo.

    ── La regla (D2 del plan): el portal DA papeles, solo la consola los QUITA ──

    Hasta F2 el pase solo decidía el rol al CREAR la fila; después mandaba el
    local (`OPERAR.md` §4.13). Estaba puesto para que un cambio en el portal no
    degradara en silencio al administrador de un campeonato en marcha — y lo
    conseguía, pero a cambio el pase con varios papeles no cambiaba nada aquí
    para nadie que ya hubiera entrado una vez. Ahora:

      · lo que el pase trae y la fila no tiene → **se añade**;
      · lo que la fila tiene y el pase no trae → **se conserva**. Es
        exactamente el degradado en silencio que la regla vieja evitaba;
      · lo que la consola QUITÓ (`roles_quitados`) → **no se devuelve**.

    ── Y lo que el pase nunca da: `admin` ──

    El mando de los campeonatos se pone a mano aquí, mirando, igual que
    `es_superadmin` (`OPERAR.md` §1.5). Y F4 ni siquiera ha contado todavía
    cuántos administradores hay por organización (D3): repartir más desde
    fuera antes de ese informe es justo lo que D3 pide no hacer. Al CREAR la
    fila el pase sí puede traerlo, como hasta hoy.

    No escribe nada para un usuario desactivado: ahí no va a entrar nadie.
    """
    if not usuario.activo:
        return False
    cerrados = set(usuario.roles) | set(usuario.roles_quitados) | {"admin"}
    nuevos = [p for p in papeles_del_pase(claims) if p not in cerrados]
    if not nuevos:
        return False
    antes = usuario.roles
    usuario.roles = antes + nuevos
    # Lo que da el portal lo puede quitar el portal (ver la función de abajo).
    usuario.roles_del_portal = usuario.roles_del_portal + nuevos
    log.info(
        "[ecosistema] %s suma %s desde su pase (tenía %s).",
        usuario.email, ", ".join(nuevos), ", ".join(antes),
    )
    return True


def _retirar_lo_que_el_portal_ya_no_da(usuario, claims):
    """
    Le quita a la fila los papeles que dio el portal y su pase ya no trae.

    Devuelve True si cambió algo.

    ── Lo que cierra (nº 5 de la PARTE 4, decidido el 25 sep 2026) ──

    Hasta aquí el portal podía DAR y solo la consola QUITAR (D2). Así, a quien
    le quitaban el papel de juez o de maestro en el portal lo conservaba aquí
    para siempre. Ahora la regla es por procedencia: **lo que dio el portal, el
    portal lo quita**; lo que se puso a mano en la consola, no. Sin canal
    nuevo: se aplica al entrar, que es cuando importa (el espejo no tiene
    contraseña que valga: solo entra con el pase).

    ── Lo que NO toca, a propósito ──

    · `admin`: el mando de los campeonatos no lo quita nadie desde fuera
      (`roles_del_portal` nunca lo guarda).
    · Lo que la consola dio o quitó (`fijar_papeles_a_mano` lo saca de la
      lista de procedencia).
    · Nada, si el pase no trae la LISTA `roles_campeonatos` (F1): un portal sin
      actualizar solo manda el papel principal, y quitar lo demás por eso sería
      degradar a la gente por un pase incompleto.

    Si no le queda ningún papel, se queda con `competidor`: entra a su panel,
    que es lo que puede ver cualquiera sobre sí mismo.
    """
    if not usuario.activo or not isinstance((claims or {}).get("roles_campeonatos"), list):
        return False
    del_pase = set(papeles_del_pase(claims))
    retirados = [
        p for p in usuario.roles_del_portal
        if p in usuario.roles and p not in del_pase
    ]
    if not retirados:
        return False
    antes = usuario.roles
    quedan = [p for p in antes if p not in retirados] or ["competidor"]
    usuario.roles = quedan
    usuario.roles_del_portal = [
        p for p in usuario.roles_del_portal if p not in retirados
    ]
    log.info(
        "[ecosistema] %s pierde %s: el portal se lo dio y su pase ya no lo trae "
        "(tenía %s).",
        usuario.email, ", ".join(retirados), ", ".join(antes),
    )
    return True


def club_del_pase(claims, pase):
    """
    El club de esa persona, preguntándoselo al ecosistema. `None` si no se sabe.

    ── Por qué se pregunta en vez de leerlo del pase ─────────────────────────

    El pase trae `org_id`, que es un identificador: aquí hace falta el NOMBRE,
    porque `usuarios.club` es texto libre y es lo que se imprime en la llave,
    en el acta y en la planilla. Meter el nombre en el token engordaría el
    contrato para las tres apps y quedaría viejo en cuanto el club se
    renombrara; preguntarlo cuesta una petición **la primera vez que entra**.

    Se pregunta **con el pase de la propia persona**, no con un secreto de
    servidor: el ecosistema le responde lo que ella ya puede ver, y aquí no
    hace falta guardar ninguna credencial más.

    **Falla hacia fuera en silencio**: si el ecosistema no contesta, se entra
    igual y sin club — exactamente como se entraba antes de esto. Lo que no
    puede pasar es que el ecosistema lento impida entrar a un maestro.
    """
    org_id = str((claims or {}).get("org_id") or "").strip()
    raiz = url_api_ecosistema()
    if not org_id or not raiz or not pase:
        return None

    try:
        peticion = Request(
            f"{raiz}/organizations/{org_id}",
            headers={"Authorization": f"Bearer {pase}"},
        )
        with urlopen(peticion, timeout=ESPERA_CLUB_SEG) as respuesta:
            org = json.loads(respuesta.read().decode("utf-8"))
    except (URLError, ValueError, OSError) as exc:
        log.warning("[ecosistema] no se pudo leer el club %s: %s", org_id, exc)
        return None

    nombre = str(org.get("name") or "").strip()
    if not nombre:
        return None
    return {
        "nombre": nombre.upper(),
        # La delegación del club, que Campeonatos usa para agrupar reportes, y
        # que el ecosistema guarda aparte de la ciudad justamente por eso.
        "ciudad": org.get("delegation") or org.get("city"),
        "pais": org.get("delegationCountry") or org.get("country"),
    }


def resolver_espejo(claims, pase=None):
    """
    La fila de `usuarios` que corresponde a ese pase.

    Devuelve `(usuario, motivo)`: con el usuario resuelto, `motivo` es `None`;
    cuando no hay usuario, `motivo` dice por qué, para que quien llame pueda
    contarlo sin inventárselo:

    · `"sin_consola"` — es quien dice ser, pero su pase no trae ningún papel
      de Campeonatos (ni opera ni compite).
    · `"correo_ocupado"` — ese correo ya es de OTRA cuenta del ecosistema.
    · `"pase_incompleto"` — el pase no trae `sub` o `email`.
    """
    if not claims:
        return None, "pase_incompleto"

    sub = str(claims.get("sub") or "").strip()
    email = str(claims.get("email") or "").strip().lower()
    if not sub or not email:
        return None, "pase_incompleto"

    # Una sola pregunta al ecosistema por entrada, la haga quien la haga: el
    # club del maestro y el nombre de la organización salen de la misma.
    club = _ClubDelPase(claims, pase)

    usuario = Usuario.query.filter_by(eco_sub=sub).first()
    if usuario:
        # Primero los papeles y después el club: si el pase lo acaba de hacer
        # maestro, esa misma entrada ya le trae su dojang.
        _sumar_papeles_del_pase(usuario, claims)
        _retirar_lo_que_el_portal_ya_no_da(usuario, claims)
        _asegurar_club(usuario, club)
        _asegurar_organizacion(usuario, claims, club)
        # Sin esto, lo que se acaba de sumar —y el club que se le puso— se
        # descartaba al terminar la petición: nadie hacía `commit` aquí.
        if db.session.dirty:
            db.session.commit()
        return usuario, None

    usuario = Usuario.query.filter_by(email=email).first()
    if usuario:
        # `str(...)` a los dos lados: en PostgreSQL la columna es `uuid`, y
        # según por dónde venga la fila esto puede ser un objeto UUID. Comparar
        # un UUID con una cadena da distinto siempre, y el resultado sería
        # decirle «ese correo ya es de otra cuenta» a quien es él mismo.
        if usuario.eco_sub and str(usuario.eco_sub) != sub:
            # Dos cuentas del ecosistema reclamando el mismo correo de aquí.
            # No se pisa ninguna: se para y que lo mire una persona.
            log.warning(
                "[ecosistema] el correo %s ya es de otro sub (%s ≠ %s).",
                email, usuario.eco_sub, sub,
            )
            return None, "correo_ocupado"
        usuario.eco_sub = sub
        _sumar_papeles_del_pase(usuario, claims)
        _asegurar_club(usuario, club)
        _asegurar_organizacion(usuario, claims, club)
        db.session.commit()
        log.info("[ecosistema] %s enlazado con su cuenta del ecosistema.", email)
        return usuario, None

    rol = rol_principal(claims)
    if not rol:
        return None, "sin_consola"

    # Con TODOS los papeles del pase, no solo el principal: el maestro que
    # además juzga nace pudiendo juzgar, sin que nadie tenga que marcarlo.
    papeles = ordenar_papeles([rol, *papeles_del_pase(claims)])
    # Un solo administrador por organización (F4). Al super-admin no se le
    # aplica: no es admin de ninguna organización, y entra sin `org_id`.
    if not es_super(claims):
        papeles = sin_admin_si_ya_hay_otro(papeles, org_del_pase(claims), sub, email)

    usuario = Usuario(
        email=email,
        nombre=(str(claims.get("fullName") or email).strip().upper())[:NOMBRE_MAX],
        rol=papeles[0],
        eco_sub=sub,
        activo=True,
    )
    usuario.roles = papeles
    # Nace con lo que trae el pase: todo es «del portal» (menos `admin`).
    usuario.roles_del_portal = papeles
    # Una contraseña que nadie conoce ni puede adivinar: el espejo no se abre
    # con contraseña, se abre con el pase. La columna es NOT NULL, así que
    # dejarla vacía no es opción — y un valor fijo sería una llave maestra.
    usuario.set_password(secrets.token_urlsafe(32))
    _asegurar_club(usuario, club)
    _asegurar_organizacion(usuario, claims, club)
    db.session.add(usuario)
    db.session.commit()
    log.info("[ecosistema] espejo creado para %s (%s).", email, usuario.rol)
    return usuario, None


class _ClubDelPase:
    """`club_del_pase`, preguntado como mucho UNA vez por entrada.

    Lo necesitan dos cosas en la misma entrada —el club del maestro y el
    nombre de la organización— y cada pregunta al ecosistema puede costar
    hasta `ESPERA_CLUB_SEG`. Solo se pregunta si alguna de las dos lo pide.
    """

    def __init__(self, claims, pase):
        self._claims = claims
        self._pase = pase
        self._preguntado = False
        self._valor = None

    def __call__(self):
        if not self._preguntado:
            self._preguntado = True
            self._valor = club_del_pase(self._claims, self._pase)
        return self._valor

    @property
    def ya_preguntado(self):
        """True si esta entrada ya le preguntó al ecosistema (y lo que diga es gratis)."""
        return self._preguntado


# A quién se le pregunta el NOMBRE de su organización. Solo al admin, que es
# quien lo ve (en la cabecera de `/admin`). Al juez no se le pregunta nada al
# ecosistema, a propósito: sería una petición por cada juez que entra la mañana
# del campeonato (ver `ROLES_CON_CLUB` y su prueba). A los demás se les guarda
# el `org_id`, que viene en el pase y no cuesta nada.
ROLES_CON_NOMBRE_DE_ORG = ("admin",)


def _asegurar_club(usuario, club):
    """
    Le pone su club al maestro que todavía no tiene ninguno.

    **Solo si no tiene**: los clubes de un maestro los edita el administrador
    desde la consola, y un maestro puede dirigir varios dojangs. Rellenar por
    encima de eso en cada inicio de sesión borraría ese trabajo en silencio —y
    con él la delegación, que es como se agrupan los reportes—.
    """
    if usuario.rol not in ROLES_CON_CLUB or usuario.clubes:
        return
    datos = club()
    if not datos:
        return
    usuario.clubes = [datos]
    log.info("[ecosistema] %s estrena club: %s", usuario.email, datos["nombre"])


def _asegurar_organizacion(usuario, claims, club):
    """
    La organización del pase, copiada a la fila (F4). En CADA entrada.

    Al revés que el club del maestro, esto sí se reescribe siempre: no lo edita
    nadie aquí, es un reflejo de dónde está la persona en el ecosistema, y si
    se cambió de club tiene que cambiar con ella.

    · Sin `org_id` en el pase —el super-admin, alguien sin pertenencia— no se
      toca lo que hubiera: «no consta» no es «no tiene».
    · El nombre se pregunta al ecosistema solo al ADMIN
      (`ROLES_CON_NOMBRE_DE_ORG`), y solo cuando cambia la organización o
      todavía no se sabe. A los demás se les pone si esta misma entrada ya
      preguntó por su club, que es gratis. Si no contesta, se entra igual.
    · Si quien entra es admin y su organización se acaba de saber, sus
      campeonatos sin organización la reciben (`rellenar_org_de_campeonatos`).
    """
    org_id = org_del_pase(claims)
    if not org_id:
        return
    cambio = org_id != usuario.org_id
    if cambio:
        usuario.org_id = org_id
        # El nombre que hubiera era el de la organización anterior.
        usuario.org_nombre = None
    if not usuario.org_nombre and (
        usuario.rol in ROLES_CON_NOMBRE_DE_ORG or club.ya_preguntado
    ):
        datos = club()
        if datos:
            usuario.org_nombre = datos["nombre"][:ORG_NOMBRE_MAX]
    if cambio and usuario.rol == "admin" and usuario.id is not None:
        # El relleno es SQL que lee `usuarios.org_id` de la base: sin el
        # `flush`, leería el valor de antes y no rellenaría nada.
        db.session.flush()
        rellenados = rellenar_org_de_campeonatos(usuario.id)
        if rellenados:
            log.info(
                "[organizacion] %d campeonato(s) de %s reciben su organización.",
                rellenados, usuario.email,
            )


def guardar_apariencia(eco_sub, tema=None, idioma=None):
    """
    El tema o el idioma que la persona acaba de elegir AQUÍ, al ecosistema.

    ── Por qué hace falta ──────────────────────────────────────────────────

    La preferencia es de la PERSONA, no de la app, y vive en el portal
    (`users.theme` y `users.locale`). Ya llegaba de allí hasta aquí dentro del
    pase, pero solo en ese sentido: quien cambiaba a modo claro **dentro de
    Campeonatos** lo cambiaba solo en Campeonatos, porque `localStorage` es por
    origen y las cuatro webs viven en subdominios distintos.

    Visto desde fuera eso es peor que no tener la función: el mismo botón, en la
    misma cuenta, unas veces se recuerda en todas partes y otras no, según en
    qué app lo pulsaste.

    ── El interruptor ──────────────────────────────────────────────────────

    `ECOSYSTEM_SYNC_SECRET`. **Sin esa variable esta función no hace nada**, y
    es deliberado: es el mismo criterio que `ECOSYSTEM_JWKS_URL` en este mismo
    módulo. Campeonatos tiene que arrancar y funcionar sin internet el día del
    evento (§1.5 de OPERAR.md), así que ninguna pieza nueva puede volverse
    obligatoria — y menos una cosmética.

    ── Falla hacia fuera en silencio ───────────────────────────────────────

    Como todo el espejo. Que el portal no conteste no puede impedir que alguien
    cambie el color de su propia pantalla: la pantalla ya cambió antes de llamar
    a esto, y lo único que se pierde es que la elección viaje a las otras apps.
    """
    secreto = os.getenv("ECOSYSTEM_SYNC_SECRET", "").strip()
    raiz = url_api_ecosistema()
    if not secreto or not raiz or not eco_sub:
        return False
    if tema is None and idioma is None:
        return False

    cuerpo = {"ecoSub": str(eco_sub)}
    if tema is not None:
        cuerpo["theme"] = tema
    if idioma is not None:
        cuerpo["locale"] = idioma

    try:
        peticion = Request(
            f"{raiz}/sync/apariencia",
            data=json.dumps(cuerpo).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-dinamyt-sync": secreto,
            },
            method="POST",
        )
        with urlopen(peticion, timeout=ESPERA_CLUB_SEG):
            return True
    except (URLError, ValueError, OSError) as exc:
        log.warning(
            "[ecosistema] la apariencia de %s no viajo a las otras apps: %s",
            eco_sub,
            exc,
        )
        return False


# ── El alta de un juez, en DINAMYT (nº 5 de la PARTE 4, 25 sep 2026) ─────────
#
# Cuánto se espera al ecosistema: el admin está delante de un formulario, y el
# alta crea una cuenta y quizá manda un correo. Más que la pregunta del club.
ESPERA_ALTA_SEG = 15


class AltaFallida(Exception):
    """El alta en DINAMYT no se hizo. `mensaje` se le enseña al admin tal cual."""

    def __init__(self, mensaje, codigo=502):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.codigo = codigo


def alta_en_dinamyt_activa():
    """
    ¿Las cuentas que se dan de alta aquí nacen en DINAMYT?

    Sí cuando está el puente ENTERO: la API del ecosistema y
    `ECOSYSTEM_SYNC_SECRET`. **No** basta con `ECOSYSTEM_JWKS_URL`: el PC del
    evento la lleva desde F8 (para entrar con DINAMYT cuando vuelve la red) y
    el día del campeonato no tiene internet. Si el alta dependiera de esa
    variable, ese día no se podría crear un juez — y romper el modo local es lo
    único que no se hace (`OPERAR.md` §1.5). El secreto del espejo no viaja en
    un portátil: solo lo tiene la instalación de internet.
    """
    return bool(os.getenv("ECOSYSTEM_SYNC_SECRET", "").strip() and url_api_ecosistema())


def alta_de_juez_en_dinamyt(email, nombre, org_id, invitado_por=None):
    """
    Crea en DINAMYT la cuenta de un juez y lo mete en la organización del admin.

    Es la misma invitación que hace el portal (`POST /sync/alta` con
    `app: campeonatos`): la persona pone su contraseña con el enlace, aquí no
    se reparte ninguna. Devuelve `{ecoSub, cuenta, invitacion}`.

    **Lanza `AltaFallida` si no se hizo**, al revés que el resto del espejo: si
    se siguiera adelante, la fila nacería suelta, que es justo lo que esto
    cierra. El mensaje de DINAMYT («una organización solo agrega
    administradores y jueces», «el usuario ya es miembro») llega tal cual.
    """
    secreto = os.getenv("ECOSYSTEM_SYNC_SECRET", "").strip()
    raiz = url_api_ecosistema()
    if not secreto or not raiz:
        raise AltaFallida("Esta instalación no está conectada a DINAMYT.", 503)
    cuerpo = {
        "ecoOrgId": org_id,
        "email": email,
        "fullName": nombre,
        "role": "juez",
        "app": "campeonatos",
        "invitadoPor": str(invitado_por) if invitado_por else None,
    }
    try:
        peticion = Request(
            f"{raiz}/sync/alta",
            data=json.dumps(cuerpo).encode("utf-8"),
            headers={"content-type": "application/json", "x-dinamyt-sync": secreto},
            method="POST",
        )
        with urlopen(peticion, timeout=ESPERA_ALTA_SEG) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8") or "{}")
    except HTTPError as exc:
        try:
            error = json.loads(exc.read().decode("utf-8") or "{}")
        except ValueError:
            error = {}
        mensaje = error.get("message") or error.get("error")
        if isinstance(mensaje, list):
            mensaje = " ".join(str(m) for m in mensaje)
        log.warning("[ecosistema] el alta de %s no se hizo (%s): %s", email, exc.code, mensaje)
        raise AltaFallida(
            str(mensaje or f"DINAMYT respondió {exc.code}."),
            400 if 400 <= exc.code < 500 else 502,
        ) from exc
    except (URLError, ValueError, OSError) as exc:
        log.warning("[ecosistema] el alta de %s no llegó a DINAMYT: %s", email, exc)
        raise AltaFallida(
            "No se pudo hablar con DINAMYT. Inténtalo de nuevo en un momento.", 502
        ) from exc
    if not isinstance(datos, dict) or not datos.get("ecoSub"):
        # Una respuesta con forma de éxito y sin cuenta es como nace una fila
        # suelta: aquí es un error, igual que allá.
        raise AltaFallida("DINAMYT no devolvió la cuenta del juez.", 502)
    return datos


def miembros_del_club(maestro_sub, persona=None):
    """
    La gente de los clubes donde este maestro es maestro o coach en DINAMYT.

    `GET /sync/miembros` por el canal servidor-a-servidor (punto 2 de lo que
    quedaba del plan, 25 sep 2026). La regla de a quién se le contesta la
    aplica DINAMYT, no esto: aquí solo se pregunta en nombre del maestro que
    tiene la sesión. Con `persona`, solo esa cuenta: es como se vuelve a
    comprobar al inscribir, sin fiarse de lo que mande el navegador.

    Devuelve la lista `[{sub, fullName, birthDate, gender, documentId, club,
    sinAcceso}]`, o **None si no se pudo preguntar** (sin el puente, o sin
    red). Quien llama lo dice; nunca inventa la respuesta.
    """
    from urllib.parse import urlencode

    secreto = os.getenv("ECOSYSTEM_SYNC_SECRET", "").strip()
    raiz = url_api_ecosistema()
    if not secreto or not raiz or not maestro_sub:
        return None
    consulta = {"maestro": str(maestro_sub)}
    if persona:
        consulta["persona"] = str(persona)
    try:
        peticion = Request(
            f"{raiz}/sync/miembros?{urlencode(consulta)}",
            headers={"x-dinamyt-sync": secreto},
            method="GET",
        )
        with urlopen(peticion, timeout=ESPERA_ALTA_SEG) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))
    except HTTPError as exc:
        log.warning("[ecosistema] los miembros del club no llegaron (%s).", exc.code)
        return None
    except (URLError, ValueError, OSError) as exc:
        log.warning("[ecosistema] no se pudo preguntar por los miembros: %s", exc)
        return None
    if not isinstance(datos, list):
        return None
    return [m for m in datos if isinstance(m, dict) and m.get("sub") and m.get("fullName")]


def avisar_invitacion_a_club(org_id, campeonato, organiza=None):
    """
    Le dice al club, en su campana de DINAMYT, que lo invitaron a un campeonato.

    `POST /sync/aviso-campeonato`. **Falla hacia fuera en silencio**, como el
    resto del espejo: la invitación ya está guardada cuando se llama esto, y un
    aviso perdido no puede deshacerla. Devuelve True si el aviso llegó, para
    que la pantalla diga la verdad («se le avisó» o no).
    """
    secreto = os.getenv("ECOSYSTEM_SYNC_SECRET", "").strip()
    raiz = url_api_ecosistema()
    if not secreto or not raiz or not org_id:
        return False
    cuerpo = {"orgId": str(org_id), "campeonato": campeonato, "organiza": organiza}
    try:
        peticion = Request(
            f"{raiz}/sync/aviso-campeonato",
            data=json.dumps(cuerpo).encode("utf-8"),
            headers={"content-type": "application/json", "x-dinamyt-sync": secreto},
            method="POST",
        )
        with urlopen(peticion, timeout=ESPERA_CLUB_SEG):
            return True
    except (URLError, ValueError, OSError) as exc:
        log.warning("[ecosistema] el club %s no recibió el aviso: %s", org_id, exc)
        return False


def buscar_clubes(texto=None, federacion=None):
    """
    El directorio de clubes del ecosistema, para invitarlos a un campeonato (F5).

    Pregunta a `GET /sync/clubes` por el canal servidor-a-servidor: el admin
    que invita ya no tiene aquí su pase —lo canjeó por la cookie al entrar—.
    Con `federacion` (la `org_id` del admin), sus clubes afiliados salen
    primero y marcados.

    Devuelve la lista `[{id, name, city, afiliado}]`, o **None si no se pudo
    preguntar**: sin `ECOSYSTEM_SYNC_SECRET` (el modo local, o una variable
    que falta) o sin red. Quien llama lo dice en pantalla —y se puede invitar
    igual escribiendo el nombre—: ningún puente nuevo se calla (§1.6-bis del
    plan).
    """
    from urllib.parse import urlencode

    secreto = os.getenv("ECOSYSTEM_SYNC_SECRET", "").strip()
    raiz = url_api_ecosistema()
    if not secreto or not raiz:
        return None
    consulta = urlencode(
        {k: v for k, v in (("search", texto), ("federacion", federacion)) if v}
    )
    try:
        peticion = Request(
            f"{raiz}/sync/clubes" + (f"?{consulta}" if consulta else ""),
            headers={"x-dinamyt-sync": secreto},
            method="GET",
        )
        with urlopen(peticion, timeout=ESPERA_CLUB_SEG) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))
    except (URLError, ValueError, OSError) as exc:
        log.warning("[ecosistema] no se pudo buscar clubes: %s", exc)
        return None
    if not isinstance(datos, list):
        return None
    return [
        {
            "org_id": str(c.get("id") or ""),
            "nombre": str(c.get("name") or "").strip().upper(),
            "ciudad": c.get("city"),
            "afiliado": bool(c.get("afiliado")),
        }
        for c in datos
        if isinstance(c, dict) and c.get("id") and c.get("name")
    ]


def leer_apariencia(eco_sub):
    """
    La VUELTA: qué tema y qué idioma tiene esa persona en su cuenta de DINAMYT.

    ── El hueco que cierra ────────────────────────────────────────────────

    `guardar_apariencia` cerró la IDA: cambiar el modo claro aquí ya se guarda
    en la cuenta. La vuelta seguía dependiendo del PASE, y el pase se firma al
    ENTRAR.

    O sea que quien cambiaba el tema en el portal y venía aquí —donde ya tenía
    la sesión abierta desde ayer, con su propia cookie— no veía nada: el pase
    que trajo el primer día decía otra cosa, y esta app no lo vuelve a ver
    nunca. Es la otra mitad exacta de «unas veces se recuerda y otras no».

    ── El mismo interruptor ───────────────────────────────────────────────

    Sin `ECOSYSTEM_SYNC_SECRET` devuelve `None` y la pantalla se queda con el
    tema que ya tenía, que es exactamente lo de antes. El día del evento, sin
    internet, esto no puede estorbar (§1.5 de OPERAR.md).

    Devuelve `{"theme": ..., "locale": ...}` o `None` si no se pudo preguntar.
    """
    secreto = os.getenv("ECOSYSTEM_SYNC_SECRET", "").strip()
    raiz = url_api_ecosistema()
    if not secreto or not raiz or not eco_sub:
        return None

    try:
        peticion = Request(
            f"{raiz}/sync/apariencia/{quote(str(eco_sub), safe='')}",
            headers={"x-dinamyt-sync": secreto},
            method="GET",
        )
        with urlopen(peticion, timeout=ESPERA_CLUB_SEG) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))
        return {
            "theme": datos.get("theme") or "sistema",
            "locale": datos.get("locale"),
        }
    except (URLError, ValueError, OSError) as exc:
        log.warning(
            "[ecosistema] no se pudo leer la apariencia de %s: %s",
            eco_sub,
            exc,
        )
        return None
