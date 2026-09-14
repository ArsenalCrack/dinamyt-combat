"""
Modelos: Competidor e Inscripcion

- Competidor: atleta registrado en el sistema (independiente del campeonato).
  Guarda las características que permiten categorizarlo automáticamente:
  fecha de nacimiento, género, grupo de cinturón y peso.
- Inscripcion: vínculo competidor ↔ campeonato. Congela un snapshot del peso
  y el cinturón al momento de inscribir (el historial no cambia si el atleta
  sube de cinturón después) y lista las modalidades en las que participa.
"""

import re
import unicodedata
from datetime import datetime, timezone
from ..extensions import db
from ..timeutil import iso_utc
from ..uid import nuevo_uid

GENEROS = ("MASCULINO", "FEMENINO")
GRUPOS_CINTURON = ("BLANCO", "PRINCIPIANTE", "INTERMEDIO", "AVANZADO", "NEGRO")

# Estado de una inscripción:
# - aceptada: participa (la crea el admin directo, o el admin aprueba la de un maestro).
# - pendiente: solicitud de un maestro por revisar (no cuenta ni entra a llaves).
# - rechazada: solicitud denegada por el admin (guarda motivo_rechazo).
ESTADOS_INSCRIPCION = ("aceptada", "pendiente", "rechazada")

# Cinturones REALES de Hapkido → grupo competitivo (misma escala del DINAMYT
# turbo). El admin elige el cinturón; el grupo se deriva SOLO, nunca se
# escribe a mano.
CINTURONES = (
    ("Blanco", "BLANCO"),
    ("Amarillo", "PRINCIPIANTE"),
    ("Naranja", "PRINCIPIANTE"),
    ("Naranja/Verde", "PRINCIPIANTE"),
    ("Verde", "INTERMEDIO"),
    ("Verde/Azul", "INTERMEDIO"),
    ("Azul", "INTERMEDIO"),
    ("Rojo", "AVANZADO"),
    ("Marrón", "AVANZADO"),
    ("Marrón/Negro", "AVANZADO"),
    ("Negro", "NEGRO"),
)


def _clave_cinturon(nombre):
    """Normaliza para comparar: sin acentos, minúsculas, separadores unificados
    (espacio, guion y barra cuentan igual: "marron negro" == "Marrón/Negro")."""
    plano = "".join(
        c for c in unicodedata.normalize("NFD", str(nombre or ""))
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[\s\-/]+", "/", plano.strip().lower())


_CINTURON_POR_CLAVE = {_clave_cinturon(n): (n, g) for n, g in CINTURONES}

# Nombres de cinturón en inglés → nombre canónico español (para importar listas
# en inglés). El grupo competitivo se deriva luego del canónico.
CINTURONES_EN = {
    "White": "Blanco",
    "Yellow": "Amarillo",
    "Orange": "Naranja",
    "Orange/Green": "Naranja/Verde",
    "Green": "Verde",
    "Green/Blue": "Verde/Azul",
    "Blue": "Azul",
    "Red": "Rojo",
    "Brown": "Marrón",
    "Brown/Black": "Marrón/Negro",
    "Black": "Negro",
}
# Los alias en inglés apuntan al mismo (nombre_canónico, grupo) que su español.
for _en, _es in CINTURONES_EN.items():
    _par = _CINTURON_POR_CLAVE.get(_clave_cinturon(_es))
    if _par:
        _CINTURON_POR_CLAVE[_clave_cinturon(_en)] = _par


def cinturones_localizados(lang="es"):
    """Nombres de cinturón para la plantilla, en el idioma pedido."""
    if lang == "en":
        return list(CINTURONES_EN.keys())
    return [n for n, _ in CINTURONES]


def normalizar_cinturon(nombre):
    """
    Devuelve (nombre_canonico, grupo) si el cinturón está en el catálogo,
    o (None, None) si no se reconoce. Acepta variantes de mayúsculas,
    acentos y separadores ("marron negro", "Naranja-Verde"...) y los nombres
    en inglés (White, Yellow, Brown/Black...).
    """
    return _CINTURON_POR_CLAVE.get(_clave_cinturon(nombre), (None, None))


class Competidor(db.Model):
    __tablename__ = "competidores"

    id = db.Column(db.Integer, primary_key=True)
    # Identidad estable entre instancias (local ↔ online). Ver app/uid.py.
    uid = db.Column(db.String(32), nullable=True, index=True, default=nuevo_uid)
    nombre_completo = db.Column(db.String(200), nullable=False)
    # Documento de identidad: identificador natural para no duplicar atletas
    # (único cuando existe; puede faltar en registros rápidos).
    documento = db.Column(db.String(30), nullable=True, unique=True, index=True)
    fecha_nacimiento = db.Column(db.Date, nullable=True)
    genero = db.Column(db.String(20), nullable=True)  # MASCULINO | FEMENINO
    # Grupo para categorizar (BLANCO..NEGRO): se DERIVA del cinturón elegido
    # (catálogo CINTURONES), no se escribe a mano.
    grupo_cinturon = db.Column(db.String(20), nullable=True)
    cinturon = db.Column(db.String(50), nullable=True)
    peso = db.Column(db.Float, nullable=True)  # kg
    club = db.Column(db.String(200), nullable=True)
    # ── De quién es esta ficha (F3 de PLAN-CAMPEONATOS, parte 3) ────────────
    #
    # El `sub` de la cuenta de DINAMYT de la persona que compite con esta
    # ficha. Es lo que convierte «ANA GÓMEZ» en «tú»: `/api/mi/*` solo enseña
    # lo que cuelga de las fichas con TU `sub`.
    #
    # Nullable, y así seguirá en la mayoría: la ficha existe ANTES que la
    # cuenta (D5). El atleta independiente compite sin DINAMYT, y el día que se
    # la crea reclama su ficha por documento y fecha de nacimiento.
    #
    # El `sub` y no `usuarios.id`, que era la otra mitad de lo que pedía el
    # plan: el id de la fila cambia entre la instalación de internet y la del
    # evento, y el `sub` es el mismo en las dos. Con él viaja en el paquete sin
    # traducir nada (F6-c).
    #
    # Texto también en PostgreSQL, a diferencia de `usuarios.eco_sub`: allí la
    # columna ya existía como `uuid` cuando llegó el código; esta nace aquí.
    # Nunca se hace JOIN entre las dos —se compara con el texto del pase—, así
    # que no hay tipos que casar. Sin `unique`: dos fichas de la misma persona
    # (una por workspace) pueden ser tuyas a la vez.
    eco_sub = db.Column(db.String(64), nullable=True, index=True)
    # Categoría Especial: en figuras recibe siempre el 1er puesto sin afectar
    # el ranking normal (el motor de figuras ya lo maneja).
    categoria_especial = db.Column(db.Boolean, default=False, nullable=True)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    # Última actualización de datos del atleta (peso, cinturón...). Al inscribir
    # a un nuevo campeonato, si esta fecha es vieja (> ventana de días) se pide
    # al admin confirmar o actualizar los datos. NULL en filas creadas antes de
    # esta columna: se usa created_at como referencia.
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=True,
    )

    inscripciones = db.relationship(
        "Inscripcion", backref="competidor", lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def to_dict(self, num_inscripciones=None):
        data = {
            "id": self.id,
            "nombre_completo": self.nombre_completo,
            "documento": self.documento,
            "fecha_nacimiento": (
                self.fecha_nacimiento.isoformat() if self.fecha_nacimiento else None
            ),
            "genero": self.genero,
            "grupo_cinturon": self.grupo_cinturon,
            "cinturon": self.cinturon,
            "peso": self.peso,
            "club": self.club,
            "categoria_especial": bool(self.categoria_especial),
            # Solo SI está enlazada, nunca a qué cuenta: el `sub` no le sirve de
            # nada a quien administra, y es lo único que abre el panel ajeno.
            "cuenta_enlazada": bool(self.eco_sub),
            "activo": self.activo,
            "created_at": iso_utc(self.created_at),
            # Filas viejas sin updated_at: la última actualización conocida
            # es su fecha de creación.
            "updated_at": iso_utc(self.updated_at or self.created_at),
        }
        if num_inscripciones is not None:
            data["num_inscripciones"] = num_inscripciones
        return data

    def __repr__(self):
        return f"<Competidor {self.nombre_completo}>"


def _origen_del_alumno(maestro, competidor):
    """{club, delegacion, pais_delegacion} del dojang del que viene el alumno.

    Un maestro puede dirigir varios dojangs, y cada uno está donde está: el
    admin que revisa la solicitud necesita ver la delegación DE ESE club, no la
    del principal. Si el club del alumno no cuadra con ninguno (datos viejos,
    o el admin le quitó ese dojang), se cae a los del maestro, que es lo que se
    enseñaba antes.
    """
    club = getattr(competidor, "club", None)
    ficha = maestro.club_por_nombre(club) if club else None
    if ficha is None:
        return {
            "club": maestro.club,
            "delegacion": maestro.delegacion,
            "pais_delegacion": maestro.pais_delegacion,
        }
    return {
        "club": ficha["nombre"],
        "delegacion": ficha["ciudad"],
        "pais_delegacion": ficha["pais"],
    }


class Inscripcion(db.Model):
    __tablename__ = "inscripciones"
    __table_args__ = (
        db.UniqueConstraint(
            "campeonato_id", "competidor_id", name="uq_inscripcion_camp_comp"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    # Identidad estable entre instancias (local ↔ online). Ver app/uid.py.
    uid = db.Column(db.String(32), nullable=True, index=True, default=nuevo_uid)
    campeonato_id = db.Column(
        db.Integer, db.ForeignKey("campeonatos.id"), nullable=False, index=True
    )
    competidor_id = db.Column(
        db.Integer, db.ForeignKey("competidores.id"), nullable=False, index=True
    )
    # Modalidades en las que participa (lista de nombres, ej. ["COMBATE"]).
    modalidades = db.Column(db.JSON, nullable=True)
    # Snapshots al inscribir: si son NULL se usa el dato actual del competidor.
    peso = db.Column(db.Float, nullable=True)
    grupo_cinturon = db.Column(db.String(20), nullable=True)
    # Moderación: las del admin nacen "aceptada"; las de un maestro "pendiente"
    # hasta que el admin las acepte/rechace (ver ESTADOS_INSCRIPCION).
    estado = db.Column(db.String(20), default="aceptada", nullable=False)
    # Quién envió la inscripción (admin o maestro). Para el audit "solicitado por".
    created_by = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    motivo_rechazo = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    autor = db.relationship("Usuario", foreign_keys=[created_by])

    @property
    def peso_efectivo(self):
        """Peso para categorizar: el de la inscripción o, si falta, el actual."""
        if self.peso is not None:
            return self.peso
        return self.competidor.peso if self.competidor else None

    @property
    def grupo_cinturon_efectivo(self):
        """Grupo de cinturón para categorizar (snapshot o el actual)."""
        if self.grupo_cinturon:
            return self.grupo_cinturon
        return self.competidor.grupo_cinturon if self.competidor else None

    def to_dict(self, include_competidor=True):
        data = {
            "id": self.id,
            "campeonato_id": self.campeonato_id,
            "competidor_id": self.competidor_id,
            "modalidades": self.modalidades or [],
            "peso": self.peso,
            "grupo_cinturon": self.grupo_cinturon,
            "peso_efectivo": self.peso_efectivo,
            "grupo_cinturon_efectivo": self.grupo_cinturon_efectivo,
            "estado": self.estado or "aceptada",
            "created_by": self.created_by,
            "motivo_rechazo": self.motivo_rechazo,
            # Datos del solicitante (para que el admin vea "solicitado por X" con
            # su club y delegación —país y ciudad— al revisar la inscripción).
            # La delegación es la DEL DOJANG del alumno, no la del maestro: si
            # dirige uno en Cali y otro en Popayán, enseñar siempre la del
            # principal sería sencillamente falso.
            "solicitante": (
                {
                    "id": self.autor.id,
                    "nombre": self.autor.nombre,
                    "rol": self.autor.rol,
                    **_origen_del_alumno(self.autor, self.competidor),
                }
                if self.autor else None
            ),
            "created_at": iso_utc(self.created_at),
        }
        if include_competidor and self.competidor:
            data["competidor"] = self.competidor.to_dict()
        return data

    def __repr__(self):
        return (
            f"<Inscripcion comp={self.competidor_id} camp={self.campeonato_id}>"
        )
