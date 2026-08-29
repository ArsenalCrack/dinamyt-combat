"""
Row Level Security: red de seguridad por workspace (solo PostgreSQL).

El aislamiento entre workspaces ya lo hace la API (`api/scoping.py` filtra por
`created_by`). Esto es la capa de debajo: el día que un endpoint nuevo se olvide
del filtro, PostgreSQL devuelve cero filas en vez de las de otro admin.

Qué NO cubre, a propósito:

- **SQLite.** No tiene RLS. El despliegue local (LAN) se queda con el filtro de
  la aplicación, que es el mismo de siempre. Todo esto es un no-op ahí.
- **Jueces y pantallas públicas.** Su flujo no está filtrado por workspace por
  diseño (un juez arbitra el campeonato del admin que lo asignó, y la pantalla
  pública muestra todos los activos). Reciben acceso total: RLS aquí acota
  admin↔admin, que es donde está el riesgo real de mezclar datos.

Cómo sabe la base "qué workspace soy": un `before_request` lee el token y lo
guarda en `flask.g`; de ahí lo copia a la conexión un listener de `after_begin`,
que salta en CADA transacción nueva. Tiene que ser en ese evento y no una sola
vez por request: los endpoints hacen `commit()` a mitad y siguen consultando, y
un `set_config` local muere con la transacción que lo fijó.
"""

from flask import g
from sqlalchemy import event, text

from .extensions import db

# Tablas cuyo dueño es `created_by` (el admin del workspace).
TABLAS_POR_CREADOR = [
    "campeonatos",
    "competidores",
    "inscripciones",
    "llaves",
    "resultados_publicados",
]

# `usuarios` se cuelga de quién creó la cuenta, no de created_by.
TABLA_USUARIOS = "usuarios"


def _es_postgres():
    return db.engine.dialect.name == "postgresql"


# ── Contexto del request ────────────────────────────────────────────────────

def fijar_contexto(workspace_id=None, acceso_total=False):
    """Fija el workspace con el que se consultará la BD en este request.

    Aplica el valor a la transacción YA abierta, además de guardarlo para las
    siguientes. Hace falta porque para cuando esto se llama la sesión suele
    tener una transacción en curso —averiguar quién es el usuario ya consultó
    la BD—, y `after_begin` no volverá a saltar hasta el próximo commit. Sin
    esta parte, un endpoint de solo lectura (que nunca hace commit) correría
    entero con el contexto por defecto: acceso total, o sea sin protección.
    """
    g.rls_workspace_id = workspace_id
    g.rls_acceso_total = acceso_total
    _aplicar_a_sesion(workspace_id, acceso_total)


def _aplicar_a_sesion(workspace_id, acceso_total):
    """Escribe el contexto en la transacción abierta. No-op fuera de Postgres."""
    if not _es_postgres():
        return
    db.session.execute(
        text(
            "SELECT set_config('app.workspace_id', :ws, true),"
            "       set_config('app.acceso_total', :at, true)"
        ),
        {
            "ws": "" if workspace_id is None else str(workspace_id),
            "at": "on" if acceso_total else "off",
        },
    )


def _contexto_actual():
    """(workspace_id, acceso_total) del request en curso.

    Fuera de un request (CLI, seeds, tests) se devuelve acceso total: son
    tareas de mantenimiento que operan sobre toda la base a conciencia.
    """
    try:
        return (
            getattr(g, "rls_workspace_id", None),
            getattr(g, "rls_acceso_total", True),
        )
    except RuntimeError:  # fuera de contexto de aplicación
        return None, True


@event.listens_for(db.session, "after_begin")
def _aplicar_contexto(session, transaction, connection):
    """Copia el contexto a la conexión al empezar cada transacción."""
    if connection.dialect.name != "postgresql":
        return
    workspace_id, acceso_total = _contexto_actual()
    connection.exec_driver_sql(
        "SELECT set_config('app.workspace_id', %s, true),"
        "       set_config('app.acceso_total', %s, true)",
        (
            "" if workspace_id is None else str(workspace_id),
            "on" if acceso_total else "off",
        ),
    )


def contexto_de_usuario(user):
    """Traduce un usuario a (workspace_id, acceso_total).

    Superadmin, jueces y peticiones sin token reciben acceso total: ninguno de
    esos flujos está acotado a un workspace (ver el docstring del módulo).
    """
    from .api.scoping import workspace_owner_id

    if user is None:
        return None, True
    if getattr(user, "es_super", False):
        return None, True
    if user.rol not in ("admin", "maestro"):
        return None, True
    return workspace_owner_id(user), False


# ── Creación de las políticas ───────────────────────────────────────────────

_FUNCIONES = """
CREATE OR REPLACE FUNCTION app_workspace_actual() RETURNS integer
  LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('app.workspace_id', true), '')::integer
  $$;
"""

_FUNCION_ACCESO = """
CREATE OR REPLACE FUNCTION app_acceso_total() RETURNS boolean
  LANGUAGE sql STABLE AS $$
    SELECT coalesce(current_setting('app.acceso_total', true), 'on') = 'on'
  $$;
"""


def _politica(tabla, columna):
    condicion = (
        f"app_acceso_total() OR {columna} = app_workspace_actual()"
    )
    return [
        f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {tabla} FORCE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS {tabla}_por_workspace ON {tabla}",
        (
            f"CREATE POLICY {tabla}_por_workspace ON {tabla} "
            f"USING ({condicion}) WITH CHECK ({condicion})"
        ),
    ]


def _sentencias():
    """Todo el DDL de las políticas, en orden."""
    sentencias = [_FUNCIONES, _FUNCION_ACCESO]
    for tabla in TABLAS_POR_CREADOR:
        sentencias += _politica(tabla, "created_by")
    # El propio admin dueño del workspace debe seguir viéndose a sí mismo, o se
    # quedaría fuera de su propia gestión de usuarios.
    sentencias += [
        f"ALTER TABLE {TABLA_USUARIOS} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {TABLA_USUARIOS} FORCE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS {TABLA_USUARIOS}_por_workspace ON {TABLA_USUARIOS}",
        (
            f"CREATE POLICY {TABLA_USUARIOS}_por_workspace ON {TABLA_USUARIOS} "
            "USING (app_acceso_total() OR creado_por_id = app_workspace_actual() "
            "       OR id = app_workspace_actual()) "
            "WITH CHECK (app_acceso_total() OR creado_por_id = app_workspace_actual() "
            "       OR id = app_workspace_actual())"
        ),
    ]

    return sentencias


def ensure_rls():
    """
    Crea (o actualiza) las políticas. Devuelve (aplicadas, fallos).

    NO propaga errores, y es deliberado: RLS es una red de seguridad, no un
    requisito para arrancar. Si el rol de conexión no es dueño de las tablas
    —caso típico en Neon o Supabase cuando la base la creó otro usuario— los
    `ALTER TABLE` fallan con "must be owner of table", y dejar que esa
    excepción suba tumbaba el despliegue entero: sin backend no hay ni sesión
    ni nada. La app funciona igual sin RLS; el filtro por workspace lo sigue
    haciendo `api/scoping.py`, que es donde siempre estuvo.

    Fuera de PostgreSQL (SQLite local) devuelve None: ahí RLS no existe.

    Cada sentencia va en su propia transacción para que un fallo no deshaga las
    que sí pasaron: es preferible RLS a medias que nada.
    """
    if not _es_postgres():
        return None

    aplicadas, fallos = 0, []
    for sentencia in _sentencias():
        try:
            with db.engine.begin() as conn:
                # Si otra transacción tiene la tabla cogida, este ALTER necesita
                # ACCESS EXCLUSIVE y se queda esperando SIN LÍMITE: el arranque
                # entero se cuelga y no hay ni un error que lo cuente. Con el
                # tope, falla en cinco segundos, cae en `fallos` y se imprime.
                # No evita el bloqueo — lo hace VISIBLE, que es lo que faltó.
                # SET LOCAL: solo dura esta transacción, no toca la conexión.
                conn.execute(text("SET LOCAL lock_timeout = '5s'"))
                conn.execute(text(sentencia))
            aplicadas += 1
        except Exception as exc:  # noqa: BLE001 — se reporta, no se propaga
            fallos.append((sentencia.strip().split("\n")[0], str(exc).split("\n")[0]))
    return aplicadas, fallos


def estado_rls():
    """(ok, motivo): ¿están las políticas realmente protegiendo?

    Existe porque RLS se puede activar y aun así no proteger nada: un rol
    SUPERUSER o con BYPASSRLS se salta las políticas sin avisar y desde fuera
    todo parece correcto.
    """
    if not _es_postgres():
        return True, "SQLite: RLS no aplica (el filtro lo hace la aplicación)."

    with db.engine.connect() as conn:
        fila = conn.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).first()
        if fila and (fila[0] or fila[1]):
            return False, (
                "el rol de conexión es SUPERUSER o tiene BYPASSRLS: se salta "
                "todas las políticas. Usa un rol normal para que RLS proteja."
            )
        faltan = conn.execute(
            text(
                "SELECT relname FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind = 'r' "
                "  AND c.relname = ANY(:tablas) "
                "  AND NOT (c.relrowsecurity AND c.relforcerowsecurity)"
            ),
            {"tablas": TABLAS_POR_CREADOR + [TABLA_USUARIOS]},
        ).scalars().all()
    if faltan:
        return False, f"sin RLS forzado: {', '.join(faltan)}"
    return True, "activo"
