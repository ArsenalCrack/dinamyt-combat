"""
Modelo: InvitacionClub — un club invitado a un campeonato (F5 de PLAN-CAMPEONATOS).

Hasta F5, que un maestro inscribiera en un campeonato era un efecto colateral
de quién había creado su cuenta (§1.4 del plan): veía los campeonatos del admin
que lo dio de alta, y ningún otro. Y el maestro que llega desde el portal —su
espejo nace sin `creado_por_id`— no veía NINGUNO: su workspace es él mismo.

Ahora es una decisión que el administrador toma campeonato a campeonato:
**invita a un club**, y los maestros de ese club ven el campeonato e inscriben.

── Dos formas de nombrar al club, y por qué ──

  · `org_id` — el club del ecosistema. Es la que abre la puerta a los maestros
    de OTRO workspace: se comprueba contra el `org_id` que trae su pase (F4),
    que no puede inventarse nadie.
  · `club_nombre` — siempre se guarda, para enseñarlo; y en el modo local, sin
    ecosistema, es lo único que hay. **Una invitación solo por nombre no abre
    ninguna puerta hacia fuera del workspace**: un nombre lo puede escribir
    cualquier admin en la ficha de cualquier maestro, así que dejar entrar por
    nombre sería dejar que un admin ajeno se colara en los campeonatos de otro
    poniéndole a su maestro el nombre de un club invitado.

── Los estados ──

  · `invitado`  — el admin lo invitó; todavía no ha inscrito a nadie.
  · `aceptado`  — el club ya envió su primera solicitud. Lo pone el sistema,
    no hay que pulsar nada: participar ES aceptar.
  · `retirado`  — el admin retiró la invitación. El club deja de ver el
    campeonato; lo que ya inscribió se queda, y lo modera el admin como
    siempre.
"""

from datetime import datetime, timezone

from ..extensions import db
from ..timeutil import iso_utc
from ..uid import nuevo_uid

ESTADOS_INVITACION = ("invitado", "aceptado", "retirado")


class InvitacionClub(db.Model):
    __tablename__ = "campeonato_clubes"

    id = db.Column(db.Integer, primary_key=True)
    # Identidad estable entre instancias: la invitación viaja en el paquete.
    uid = db.Column(db.String(32), nullable=True, index=True, default=nuevo_uid)
    campeonato_id = db.Column(
        db.Integer, db.ForeignKey("campeonatos.id"), nullable=False, index=True
    )
    # El club del ecosistema. NULL = invitado solo por nombre (modo local).
    org_id = db.Column(db.String(64), nullable=True, index=True)
    club_nombre = db.Column(db.String(150), nullable=False)
    club_ciudad = db.Column(db.String(120), nullable=True)
    estado = db.Column(db.String(20), default="invitado", nullable=False)
    invitado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    campeonato = db.relationship(
        "Campeonato",
        backref=db.backref(
            "invitaciones", lazy="dynamic", cascade="all, delete-orphan"
        ),
    )
    invitado_por = db.relationship("Usuario", foreign_keys=[invitado_por_id])

    @property
    def vigente(self) -> bool:
        """True si todavía abre la puerta (no se retiró)."""
        return self.estado in ("invitado", "aceptado")

    def to_dict(self):
        return {
            "id": self.id,
            "uid": self.uid,
            "campeonato_id": self.campeonato_id,
            "org_id": self.org_id,
            "club_nombre": self.club_nombre,
            "club_ciudad": self.club_ciudad,
            "estado": self.estado,
            # Si abre la puerta a maestros de fuera del workspace, o si es solo
            # un nombre (ver la cabecera del módulo).
            "por_organizacion": bool(self.org_id),
            "invitado_por": self.invitado_por.nombre if self.invitado_por else None,
            "created_at": iso_utc(self.created_at),
        }

    def __repr__(self):
        return f"<InvitacionClub {self.club_nombre} → {self.campeonato_id} ({self.estado})>"
