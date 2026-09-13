"""
Jerarquía y aislamiento de workspaces.

Tres niveles:
- superadmin (usuarios.es_superadmin): ve y gestiona TODO. Es el admin
  sembrado (seed_admin) y el único que puede crear otros administradores.
- admin: solo ve su propio workspace — los jueces, campeonatos y competidores
  que ÉL creó (columnas creado_por_id / created_by).
- juez: sin panel de administración; su flujo (mis-tatamis, tatami en vivo)
  no se filtra por workspace.

Los endpoints PÚBLICOS (campeonatos/publico, socket rol=pantalla) NUNCA se
filtran: el público ve todos los campeonatos activos sin importar el dueño.

Regla de visibilidad al negar: se responde 404 (no 403) cuando un admin
intenta acceder a un recurso de otro workspace, para no revelar su existencia.
"""

from flask_jwt_extended import get_jwt_identity

from ..models.usuario import Usuario


def usuario_actual():
    """Usuario autenticado del request (o None si el token no resuelve)."""
    try:
        uid = get_jwt_identity()
        if uid is None:
            return None
        return Usuario.query.get(int(uid))
    except (TypeError, ValueError):
        return None


def require_admin():
    """Admin activo (normal o superadmin), o None.

    Por `tiene_rol` y no por `rol`, y da exactamente lo mismo: `admin` es el
    papel de más rango, así que quien lo tiene lo tiene de principal.
    """
    user = usuario_actual()
    if not user or not user.tiene_rol("admin") or not user.activo:
        return None
    return user


def require_maestro():
    """Maestro activo, o None.

    **Este sigue preguntando por el PRINCIPAL, a propósito.** Con `tiene_rol`,
    un administrador que además es maestro entraría a los endpoints del maestro
    — que miran el workspace del admin que LO CREÓ (`workspace_owner_id`), no el
    suyo propio. Dejaría de ver sus campeonatos sin que nadie lo decidiera. F2
    no cambia a qué entra nadie.
    """
    user = usuario_actual()
    if not user or user.rol != "maestro" or not user.activo:
        return None
    return user


def workspace_owner_id(user):
    """Id del admin dueño del workspace del usuario.

    Un maestro pertenece al workspace del admin que lo creó: los campeonatos a
    los que inscribe y los alumnos que registra viven bajo ESE admin. Para el
    resto de usuarios el dueño del workspace es él mismo.
    """
    if user is None:
        return -1
    if user.rol == "maestro":
        return user.creado_por_id or user.id
    return user.id


def es_dueno_campeonato(user, camp):
    """Superadmin siempre; un admin (o maestro) solo los campeonatos de su
    workspace. El maestro tiene acceso de LECTURA a los campeonatos de su
    admin; los cambios de estado y la moderación siguen siendo del admin."""
    if user is None or camp is None:
        return False
    if user.es_super:
        return True
    return camp.created_by == workspace_owner_id(user)


def es_dueno_competidor(user, comp):
    """Superadmin siempre; un admin (o maestro de su workspace) solo los
    competidores registrados bajo ese workspace."""
    if user is None or comp is None:
        return False
    if user.es_super:
        return True
    return comp.created_by == workspace_owner_id(user)


def es_dueno_usuario(user, target):
    """Superadmin siempre; un admin solo los usuarios que él creó (y a sí mismo)."""
    if user is None or target is None:
        return False
    if user.es_super:
        return True
    return target.creado_por_id == user.id or target.id == user.id


def filtrar_campeonatos(user, query):
    """Restringe un query de Campeonato al workspace del usuario."""
    from ..models.campeonato import Campeonato

    if user is not None and user.es_super:
        return query
    return query.filter(Campeonato.created_by == workspace_owner_id(user))


def filtrar_competidores(user, query):
    """Restringe un query de Competidor al workspace del usuario."""
    from ..models.competidor import Competidor

    if user is not None and user.es_super:
        return query
    return query.filter(Competidor.created_by == workspace_owner_id(user))
