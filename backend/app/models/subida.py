"""
Modelo: SubidaResultados — qué se subió a internet de cada campeonato (F8).

Vive en la instalación del EVENTO. Una fila por campeonato (`export_uuid`):
la huella de los últimos resultados que llegaron a internet, cuándo, quién los
subió, y el rastro de los intentos que fallaron.

── Por qué no guarda copias de los resultados ──

El plan pedía una cola con el `payload` de cada podio. Aquí no hace falta:
lo que se sube se construye en el momento de subirlo
(`api/resultados.sobre_de_resultados`), así que siempre es lo último, y
«pendiente» es sencillamente todo campeonato cuyos resultados de HOY no
coinciden con los últimos que llegaron. Una cola con copias se puede quedar
vieja —el podio corregido después de encolarlo—; una huella no.
"""

from datetime import datetime, timezone

from ..extensions import db
from ..timeutil import iso_utc


class SubidaResultados(db.Model):
    __tablename__ = "subidas_resultados"

    id = db.Column(db.Integer, primary_key=True)
    export_uuid = db.Column(db.String(64), unique=True, nullable=False, index=True)
    campeonato_id = db.Column(db.Integer, nullable=True)
    nombre = db.Column(db.String(255), nullable=True)
    # Huella (sha256) de los resultados que llegaron la última vez. NULL =
    # nunca llegó nada.
    huella_enviada = db.Column(db.String(64), nullable=True)
    enviado_at = db.Column(db.DateTime, nullable=True)
    enviado_por = db.Column(db.String(255), nullable=True)
    intentos = db.Column(db.Integer, default=0, nullable=False)
    ultimo_intento_at = db.Column(db.DateTime, nullable=True)
    proximo_intento_at = db.Column(db.DateTime, nullable=True)
    ultimo_error = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            "export_uuid": self.export_uuid,
            "campeonato_id": self.campeonato_id,
            "nombre": self.nombre,
            "enviado_at": iso_utc(self.enviado_at),
            "enviado_por": self.enviado_por,
            "intentos": self.intentos,
            "ultimo_intento_at": iso_utc(self.ultimo_intento_at),
            "ultimo_error": self.ultimo_error,
        }


def ahora():
    return datetime.now(timezone.utc).replace(tzinfo=None)
