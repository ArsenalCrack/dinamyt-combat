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

import logging
import secrets

from .extensions import db
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


def rol_operativo(claims):
    """El rol que tendría en Campeonatos, o `None` si no opera nada."""
    if not claims:
        return None
    return ROL_DESDE_ECOSISTEMA.get((claims.get("role_campeonatos") or "").strip())


def resolver_espejo(claims):
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
        return usuario, None

    usuario = Usuario.query.filter_by(email=email).first()
    if usuario:
        if usuario.eco_sub and usuario.eco_sub != sub:
            # Dos cuentas del ecosistema reclamando el mismo correo de aquí.
            # No se pisa ninguna: se para y que lo mire una persona.
            log.warning(
                "[ecosistema] el correo %s ya es de otro sub (%s ≠ %s).",
                email, usuario.eco_sub, sub,
            )
            return None, "correo_ocupado"
        usuario.eco_sub = sub
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
    db.session.add(usuario)
    db.session.commit()
    log.info("[ecosistema] espejo creado para %s (%s).", email, rol)
    return usuario, None
