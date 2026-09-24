"""
La organización del ecosistema, dentro de Campeonatos (F4 de PLAN-CAMPEONATOS).

Hasta F4 no había `org_id` en ninguna tabla (§1.3 del plan): el aislamiento era
—y sigue siendo— por workspace, «quién creó esta fila». Este módulo trae la
organización sin cambiar eso:

  · `usuarios.org_id` / `org_nombre`: se copian del pase en cada entrada desde
    el portal (`espejo.py`).
  · `campeonatos.org_id`: el de su creador, al crearlo y, para los viejos, en
    cuanto se conoce el del creador (`rellenar_org_de_campeonatos`).
  · La regla del **administrador único por organización** (D3): al CREAR el
    espejo de un admin cuya organización ya tiene otro, entra sin el papel de
    admin y queda en el registro. A nadie que ya estaba se le quita nada.
  · El **informe** de las organizaciones con más de un admin, que es lo que D3
    pide mirar antes de decidir nada.

── Lo que F4 NO cambia, y por qué ──

El plan pedía que `es_dueno_campeonato` comparase `org_id` cuando las dos filas
lo tuvieran. No se hizo, a propósito:

  1. **RLS filtra por `created_by`.** Si la API dejase a un segundo admin de la
     misma organización tocar el campeonato del primero, PostgreSQL le seguiría
     escondiendo sus llaves, sus fichas y sus resultados: una consola a medias,
     peor que ninguna.
  2. **Sería un cambio por sorpresa**, justo lo que D3 pide no hacer: hoy dos
     admins del mismo club no se ven, y con la regla nueva empezarían a verse
     el uno al otro sin que nadie lo decidiera.
  3. **Con un solo admin por organización, las dos reglas dicen lo mismo.** Que
     es a donde lleva la regla de arriba.

`org_id` se guarda ya —el informe y F5 lo necesitan—, pero todavía no decide
quién es dueño de qué.
"""

import logging

from sqlalchemy import text

from .extensions import db

log = logging.getLogger(__name__)

ORG_ID_MAX = 64
ORG_NOMBRE_MAX = 150


def org_del_pase(claims):
    """El `org_id` que trae el pase (su pertenencia principal), o None."""
    valor = str((claims or {}).get("org_id") or "").strip()
    return valor[:ORG_ID_MAX] or None


def rellenar_org_de_campeonatos(creador_id=None):
    """Pone a los campeonatos sin organización la de su creador. Idempotente.

    Solo escribe donde `org_id` es NULL y el creador ya tiene la suya: un
    campeonato con organización no se cambia nunca desde aquí (el creador puede
    haber cambiado de club después, y el campeonato sigue siendo de quien lo
    organizó). Devuelve cuántos rellenó.

    Con `creador_id`, solo los de esa persona —lo que se hace cuando un admin
    entra y se acaba de saber su organización—; sin él, todos, al arrancar.
    """
    filtro = "AND created_by = :creador" if creador_id is not None else ""
    resultado = db.session.execute(
        text(
            "UPDATE campeonatos SET org_id = ("
            "  SELECT u.org_id FROM usuarios u WHERE u.id = campeonatos.created_by"
            ") "
            "WHERE org_id IS NULL "
            f"{filtro} "
            "AND EXISTS (SELECT 1 FROM usuarios u "
            "            WHERE u.id = campeonatos.created_by AND u.org_id IS NOT NULL)"
        ),
        {"creador": creador_id} if creador_id is not None else {},
    )
    return resultado.rowcount or 0


def otro_admin_de_la_organizacion(org_id, eco_sub):
    """El admin activo de esa organización que NO es esta cuenta, o None.

    Por `rol` y basta: `admin` es el papel de más rango, así que quien lo tiene
    lo tiene de principal (ver `require_admin`). Y excluye por `eco_sub` y no
    por id, porque se pregunta ANTES de que exista la fila de quien entra.
    """
    from .models.usuario import Usuario

    if not org_id:
        return None
    candidatos = Usuario.query.filter(
        Usuario.org_id == org_id,
        Usuario.activo.is_(True),
        Usuario.rol == "admin",
    ).all()
    for usuario in candidatos:
        if str(usuario.eco_sub or "") != str(eco_sub or ""):
            return usuario
    return None


def sin_admin_si_ya_hay_otro(papeles, org_id, eco_sub, email):
    """Los papeles con los que NACE un espejo, aplicando la regla del admin único.

    Si el pase trae `admin` y su organización ya tiene otro admin activo, la
    persona entra sin ese papel —y con `maestro` si no le queda ninguno—, y el
    hecho queda en el registro. **No se falla la entrada**: el segundo admin
    entra, trabaja, y alguien lo mira (punto 4 de F4). El informe lo enseña.

    Solo se aplica al CREAR la fila: a quien ya estaba no se le toca nada, y
    el pase nunca le da `admin` a una fila existente (F2).
    """
    if "admin" not in papeles or not org_id:
        return papeles
    otro = otro_admin_de_la_organizacion(org_id, eco_sub)
    if otro is None:
        return papeles
    restantes = [p for p in papeles if p != "admin"] or ["maestro"]
    log.warning(
        "[organizacion] %s pidió entrar como admin de %s, que ya tiene a %s: "
        "entra como %s (regla del administrador único, F4).",
        email, org_id, otro.email, restantes[0],
    )
    return restantes


def informe_de_administradores():
    """Lo que D3 pide mirar antes de decidir nada: quién administra qué.

    {
      "varios":     [{org_id, org_nombre, admins: [{id, nombre, email}]}],
      "con_uno":    N,   organizaciones con exactamente un admin
      "sin_organizacion": [{id, nombre, email}],  admins aún sin org_id
    }

    Solo cuenta admins ACTIVOS y deja fuera al superadministrador: no es admin
    de ninguna organización, es el de la instalación.
    """
    from .models.usuario import Usuario

    admins = (
        Usuario.query.filter(Usuario.activo.is_(True), Usuario.rol == "admin")
        .order_by(Usuario.nombre)
        .all()
    )
    por_org = {}
    sin_org = []
    for admin in admins:
        if admin.es_super:
            continue
        ficha = {"id": admin.id, "nombre": admin.nombre, "email": admin.email}
        if not admin.org_id:
            sin_org.append(ficha)
            continue
        grupo = por_org.setdefault(
            admin.org_id, {"org_id": admin.org_id, "org_nombre": None, "admins": []}
        )
        grupo["org_nombre"] = grupo["org_nombre"] or admin.org_nombre
        grupo["admins"].append(ficha)

    varios = [g for g in por_org.values() if len(g["admins"]) > 1]
    varios.sort(key=lambda g: (g["org_nombre"] or "", g["org_id"]))
    return {
        "varios": varios,
        "con_uno": sum(1 for g in por_org.values() if len(g["admins"]) == 1),
        "sin_organizacion": sin_org,
    }
