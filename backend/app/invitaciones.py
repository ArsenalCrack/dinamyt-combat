"""
Por qué puerta entra un maestro a un campeonato (F5 de PLAN-CAMPEONATOS).

Hay dos, y se SUMAN:

  · **«De la casa»** — el campeonato es del workspace del admin que creó al
    maestro (`workspace_owner_id`). Es como funcionaba todo antes de F5, y se
    conserva entera: es la «migración blanda» del punto 4 del plan —nadie
    pierde acceso el día del despliegue—, y es además como trabaja el modo
    local, donde no hay ecosistema y todos los maestros los crea el admin de
    esa instalación.
  · **«Invitado»** — el administrador invitó a su CLUB, por `org_id`. Es la
    puerta nueva, y la única por la que entra el maestro que llega desde el
    portal: su espejo nace sin `creado_por_id`, así que «de la casa» no le
    abría nada.

Una invitación solo por NOMBRE no abre la segunda puerta (ver la cabecera de
`models/invitacion.py`): un nombre lo puede escribir cualquier admin en la
ficha de cualquier maestro.

Todo lo que se lee aquí se lee **con la red de RLS levantada** y filtrando a
mano: el maestro invitado no ve, con su propio contexto, ni el campeonato al
que lo invitaron. Lo que acota es el filtro explícito por su `org_id`.
"""

from .api.scoping import workspace_owner_id
from .extensions import db
from .models.campeonato import Campeonato
from .models.invitacion import InvitacionClub
from .rls import sin_workspace

ESTADOS_VIGENTES = ("invitado", "aceptado")

CASA = "casa"
INVITADO = "invitado"

NO_INVITADO = "Tu club no está invitado a este campeonato."


def invitaciones_de(maestro):
    """Las invitaciones VIGENTES a la organización de este maestro."""
    if not maestro or not maestro.org_id:
        return []
    with sin_workspace():
        return (
            InvitacionClub.query.filter(
                InvitacionClub.org_id == maestro.org_id,
                InvitacionClub.estado.in_(ESTADOS_VIGENTES),
            ).all()
        )


def campeonato_para_el_maestro(maestro, camp_id):
    """(campeonato, puerta, invitacion, error, codigo).

    `puerta` es CASA o INVITADO. Con error, el código es:

      · 404 — el campeonato no existe o no está activo;
      · 403 — existe y está publicado, pero su club no está invitado. Con una
        frase que se pueda leer (punto 3 de F5), no un 404 mudo: el
        campeonato activo ya es público (`/campeonatos/publico`), así que
        decir que existe no revela nada.
    """
    with sin_workspace():
        camp = db.session.get(Campeonato, camp_id)
        if camp is None or not camp.activo:
            return None, None, None, "Campeonato no encontrado", 404
        if camp.created_by == workspace_owner_id(maestro):
            return camp, CASA, None, None, None
        invitacion = None
        if maestro.org_id:
            invitacion = InvitacionClub.query.filter(
                InvitacionClub.campeonato_id == camp.id,
                InvitacionClub.org_id == maestro.org_id,
                InvitacionClub.estado.in_(ESTADOS_VIGENTES),
            ).first()
    if invitacion is None:
        return None, None, None, NO_INVITADO, 403
    return camp, INVITADO, invitacion, None, None


def marcar_aceptada(invitacion):
    """Participar ES aceptar: la primera solicitud del club la pasa a `aceptado`."""
    if invitacion is not None and invitacion.estado == "invitado":
        invitacion.estado = "aceptado"
