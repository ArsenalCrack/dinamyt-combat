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
3. **No existe**: se crea, **solo si el pase trae un rol que opere**.

── Un alumno no crea usuario aquí, y es una decisión ────────────────────────

Campeonatos es una consola de operación: administra, inscribe o puntúa. Un
alumno de un club afiliado tiene el plan —su federación lo paga— pero no tiene
nada que hacer dentro, así que su pase no crea ninguna fila. Lo suyo (sus
campeonatos, sus resultados) se ve en el portal, que es donde vive.

Sin esto, la primera vez que una federación con doscientos alumnos abriera
DINAMYT, esta tabla tendría doscientas filas de gente que no va a entrar
nunca, y cada una consumiendo un correo único.

── El rol local manda sobre el del pase ─────────────────────────────────────

El pase dice qué rol tiene la persona en su club; la fila local dice qué es en
ESTA aplicación, y puede haber sido puesto a mano por el administrador. Al
crear el espejo se toma el del pase, porque no hay otra cosa; a partir de ahí
manda el local. Es el mismo criterio que Academy, y evita que un cambio de rol
en el portal degrade en silencio al administrador de un campeonato en marcha.

`es_superadmin` **nunca** viaja en este camino: se concede a mano, mirando.
"""

import json
import logging
import secrets
from urllib.error import URLError
from urllib.request import Request, urlopen

from .extensions import db
from .identidad import url_api_ecosistema
from .models.usuario import Usuario

log = logging.getLogger(__name__)

# Del catálogo del ecosistema al de aquí. Los que faltan —`competitor`,
# `student`, `guardian`, `member`— no operan nada: no abren la consola.
ROL_DESDE_ECOSISTEMA = {
    "admin": "admin",
    "maestro": "maestro",
    # En el ecosistema, el `coach` del club es quien inscribe a los suyos: eso
    # aquí se llama maestro.
    "coach": "maestro",
    "judge": "juez",
    "juez": "juez",
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


def rol_operativo(claims):
    """El rol que tendría en Campeonatos, o `None` si no opera nada."""
    if not claims:
        return None
    propio = ROL_DESDE_ECOSISTEMA.get((claims.get("role_campeonatos") or "").strip())
    if propio:
        return propio
    # El super-admin entra a administrar aunque no sea miembro de ningún club.
    return "admin" if es_super(claims) else None


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

    · `"sin_consola"` — es quien dice ser, pero su rol no opera aquí.
    · `"correo_ocupado"` — ese correo ya es de OTRA cuenta del ecosistema.
    · `"pase_incompleto"` — el pase no trae `sub` o `email`.
    """
    if not claims:
        return None, "pase_incompleto"

    sub = str(claims.get("sub") or "").strip()
    email = str(claims.get("email") or "").strip().lower()
    if not sub or not email:
        return None, "pase_incompleto"

    usuario = Usuario.query.filter_by(eco_sub=sub).first()
    if usuario:
        _asegurar_club(usuario, claims, pase)
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
        _asegurar_club(usuario, claims, pase)
        db.session.commit()
        log.info("[ecosistema] %s enlazado con su cuenta del ecosistema.", email)
        return usuario, None

    rol = rol_operativo(claims)
    if not rol:
        return None, "sin_consola"

    usuario = Usuario(
        email=email,
        nombre=(str(claims.get("fullName") or email).strip().upper())[:NOMBRE_MAX],
        rol=rol,
        eco_sub=sub,
        activo=True,
    )
    # Una contraseña que nadie conoce ni puede adivinar: el espejo no se abre
    # con contraseña, se abre con el pase. La columna es NOT NULL, así que
    # dejarla vacía no es opción — y un valor fijo sería una llave maestra.
    usuario.set_password(secrets.token_urlsafe(32))
    _asegurar_club(usuario, claims, pase)
    db.session.add(usuario)
    db.session.commit()
    log.info("[ecosistema] espejo creado para %s (%s).", email, rol)
    return usuario, None


def _asegurar_club(usuario, claims, pase):
    """
    Le pone su club al maestro que todavía no tiene ninguno.

    **Solo si no tiene**: los clubes de un maestro los edita el administrador
    desde la consola, y un maestro puede dirigir varios dojangs. Rellenar por
    encima de eso en cada inicio de sesión borraría ese trabajo en silencio —y
    con él la delegación, que es como se agrupan los reportes—.
    """
    if usuario.rol not in ROLES_CON_CLUB or usuario.clubes:
        return
    club = club_del_pase(claims, pase)
    if not club:
        return
    usuario.clubes = [club]
    log.info("[ecosistema] %s estrena club: %s", usuario.email, club["nombre"])
