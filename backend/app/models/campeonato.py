"""
Modelo: Campeonato
Un campeonato agrupa tatamis y tiene fechas.
Soporta múltiples campeonatos simultáneos.
"""

from datetime import datetime, timezone
from ..extensions import db
from ..timeutil import iso_utc
from ..uid import nuevo_uid

# Ciclo de vida del campeonato (independiente de `activo`, que controla la
# visibilidad pública):
# - preparacion: abierto a solicitudes de inscripción de los maestros.
# - en_curso: la competencia está corriendo; se cierran las solicitudes de
#   maestros (el admin sigue pudiendo inscribir directo).
# - finalizado: terminó.
ESTADOS_CAMPEONATO = ("preparacion", "en_curso", "finalizado")


class Campeonato(db.Model):
    __tablename__ = "campeonatos"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(255), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    fecha_inicio = db.Column(db.Date, nullable=True)
    fecha_fin = db.Column(db.Date, nullable=True)
    # Sede/ciudad/país: detalles que ve el público en la ficha del campeonato.
    lugar = db.Column(db.String(120), nullable=True)
    ciudad = db.Column(db.String(120), nullable=True)
    pais = db.Column(db.String(120), nullable=True)
    # Estado del ciclo de vida (ver ESTADOS_CAMPEONATO). Default preparacion.
    estado = db.Column(db.String(20), default="preparacion", nullable=False)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    # Config de categorías por modalidad para la generación automática de
    # llaves: {"modalidades": [{nombre, tipo, activa, categorias: {...}}]}.
    # NULL = el admin todavía no configuró (el flujo manual no la necesita).
    config_categorias = db.Column(db.JSON, nullable=True)
    # UUID estable del campeonato: es su identidad al viajar entre instancias
    # (ver app/uid.py). Permite que reimportar el mismo campeonato lo ACTUALICE
    # en vez de duplicarlo, tanto al publicar solo los resultados
    # (api/resultados.py) como al traspasar el campeonato completo
    # (api/sincronizacion.py). Los campeonatos anteriores a esta columna lo
    # reciben en el backfill de arranque.
    export_uuid = db.Column(
        db.String(64), nullable=True, index=True, default=nuevo_uid
    )
    created_by = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=True
    )
    # La organización del ecosistema que lo organiza (F4): la de quien lo
    # creó, copiada al crearlo. NULL = «del workspace de siempre» —creado antes
    # de F4, o en el modo local— y sigue funcionando por `created_by`, que es
    # quien decide de quién es. `org_id` todavía NO decide nada: lo usa F5 para
    # saber quién invita a quién, y el día que haya un solo administrador por
    # organización las dos cosas dirán lo mismo (ver PLAN-CAMPEONATOS, F4).
    org_id = db.Column(db.String(64), nullable=True, index=True)
    # «Solo clubes invitados» (punto 3 de lo que quedaba del plan, 25 sep 2026).
    # Con esto encendido se cierra la puerta vieja —«el campeonato es del admin
    # que me creó»—: entra solo el club que esté en «Clubes invitados», por su
    # organización o, dentro del propio workspace, por su nombre. Apagado es
    # como siempre, y NULL (bases viejas) cuenta como apagado.
    solo_invitados = db.Column(db.Boolean, default=False, nullable=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relaciones
    tatamis = db.relationship(
        "Tatami", backref="campeonato", lazy="dynamic", cascade="all, delete-orphan"
    )
    inscripciones = db.relationship(
        "Inscripcion", backref="campeonato", lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(self, include_tatamis=False):
        # Solo las inscripciones ACEPTADAS cuentan (las pendientes son
        # solicitudes de maestros por revisar; las rechazadas no participan).
        num_aceptadas = self.inscripciones.filter_by(estado="aceptada").count()
        num_pendientes = self.inscripciones.filter_by(estado="pendiente").count()
        data = {
            "id": self.id,
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "fecha_inicio": self.fecha_inicio.isoformat() if self.fecha_inicio else None,
            "fecha_fin": self.fecha_fin.isoformat() if self.fecha_fin else None,
            "lugar": self.lugar,
            "ciudad": self.ciudad,
            "pais": self.pais,
            "estado": self.estado or "preparacion",
            "activo": self.activo,
            "created_by": self.created_by,
            "org_id": self.org_id,
            "solo_invitados": bool(self.solo_invitados),
            "created_at": iso_utc(self.created_at),
            "num_tatamis": self.tatamis.count() if self.tatamis else 0,
            "num_inscripciones": num_aceptadas,
            "num_pendientes": num_pendientes,
        }
        if include_tatamis:
            data["tatamis"] = [t.to_dict() for t in self.tatamis.all()]
            data["config_categorias"] = self.config_categorias
        return data

    def __repr__(self):
        return f"<Campeonato {self.nombre}>"
