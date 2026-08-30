"""
Modelo: Usuario
Roles: admin (gestiona campeonatos, tatamis, jueces) | maestro (inscribe a sus
alumnos y, si el admin se lo permite, puntúa como juez) | juez (puntúa combates)
"""

import os
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import UUID as PgUUID

from ..extensions import db
from ..timeutil import iso_utc
from ..uid import nuevo_uid
import bcrypt

# Roles válidos del sistema. `rol` es un String (no Enum de BD) para poder
# ampliar la lista sin migrar el tipo en bases existentes; la validez se
# comprueba en la API. La jerarquía admin>maestro>juez se apoya además en
# `es_superadmin` (booleano aparte) y en `creado_por_id` (workspace).
ROLES_VALIDOS = ("admin", "maestro", "juez")

# Costo (rondas) de bcrypt al hashear contraseñas. 12 (el default de la
# librería) tarda ~0.5 s en un PC y 1.5–3 s en la CPU compartida del plan
# gratis de Render: cada login se siente lento y, bajo eventlet de un solo
# worker, bloquea TODO el proceso mientras calcula. 10 rondas siguen siendo
# seguras y son ~4× más rápidas. Ajustable por entorno si se quiere más costo.
BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "10"))


class Usuario(db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    # Identidad estable entre instancias (local ↔ online). Ver app/uid.py.
    uid = db.Column(db.String(32), nullable=True, index=True, default=nuevo_uid)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    # El `sub` de la cuenta en el ecosistema: lo que convierte esta fila en un
    # ESPEJO de esa cuenta y no en una cuenta propia (C3 del plan). Nullable
    # porque la mayoría de las filas nacieron antes de la identidad única y se
    # enlazan por correo la primera vez que su dueño entra desde el portal.
    #
    # ── `uuid` en PostgreSQL, texto en SQLite, y no es un capricho ──
    #
    # En producción esta columna YA EXISTÍA cuando se escribió esto: la creó el
    # guion de reconciliación del 29 de agosto —como `uuid`, con su índice
    # único— y dejó 12 de los 22 usuarios ya enlazados. Declararla `String` a
    # secas funcionaba para buscar (PostgreSQL convierte el literal), pero la
    # LECTURA devolvía un objeto `UUID`, y comparar ese objeto con la cadena
    # del pase da distinto SIEMPRE: el enlace por correo habría contestado
    # «ese correo ya es de otra cuenta» a gente que era ella misma.
    #
    # Con la variante, PostgreSQL usa su tipo nativo y devuelve texto
    # (`as_uuid=False`), y SQLite —el modo local— sigue con VARCHAR.
    #
    # Sin `unique` declarado aquí a propósito: en SQLite, añadir una
    # restricción a una tabla existente obliga a reconstruirla entera. En
    # producción el índice único ya lo puso la reconciliación.
    eco_sub = db.Column(
        db.String(64).with_variant(PgUUID(as_uuid=False), "postgresql"),
        nullable=True,
        index=True,
    )
    nombre = db.Column(db.String(150), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    # String (no Enum de BD): en SQLite el Enum se guarda como VARCHAR sin
    # CHECK y ampliar la lista de roles no requiere migración de tipo. La
    # validez del valor la impone la API (ver ROLES_VALIDOS).
    rol = db.Column(db.String(20), nullable=False, default="juez")
    # Jerarquía: superadmin > admin > juez. El superadmin (el admin sembrado)
    # ve y gestiona TODO; un admin normal solo su propio workspace (los jueces,
    # campeonatos y competidores que él creó). Booleano aparte y no un tercer
    # valor del Enum para no requerir migración del tipo en bases existentes.
    es_superadmin = db.Column(db.Boolean, default=False, nullable=True)
    # ── Clubes del maestro ──────────────────────────────────────────────────
    #
    # Un maestro puede dirigir VARIOS dojangs, y un mismo club puede tener
    # varios maestros. Lo segundo siempre funcionó (nunca hubo unicidad sobre
    # el nombre del club); lo primero no cabía en una sola columna de texto.
    #
    # `clubes` (JSON) es la lista completa y la fuente de verdad. Cada dojang
    # lleva SU PROPIA delegación —ciudad y país—, porque los dojangs de un
    # mismo maestro suelen estar en sitios distintos: uno en Cali y otro en
    # Popayán no son la misma delegación, y con una sola por maestro había que
    # elegir cuál de las dos mentir.
    #
    #     [{"nombre": "DOJANG SUR", "ciudad": "Cali", "pais": "Colombia"}, ...]
    #
    # `club`, `delegacion` y `pais_delegacion` se quedan como los del club
    # PRINCIPAL —el primero de la lista— porque hay mucho que ya los lee así:
    # los paquetes de sincronización y las instalaciones que todavía no tienen
    # la columna nueva. Los mantiene en su sitio el setter de `clubes`, así que
    # no hay dos verdades que puedan discrepar: se escribe siempre por la lista.
    #
    # Las filas anteriores a la columna tienen `clubes` NULL y el getter las
    # arma con esas tres columnas, así que no hace falta ningún backfill.
    club = db.Column(db.String(80), nullable=True)
    _clubes = db.Column("clubes", db.JSON, nullable=True)
    delegacion = db.Column(db.String(120), nullable=True)
    pais_delegacion = db.Column(db.String(80), nullable=True)
    # Permiso extra para que un maestro también pueda ser asignado a un tatami
    # como juez (sin necesidad de una segunda cuenta). Solo aplica a maestros.
    puede_juzgar = db.Column(db.Boolean, default=False, nullable=True)
    activo = db.Column(db.Boolean, default=True, nullable=False)
    creado_por_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), nullable=True, index=True
    )
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    eliminado_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relaciones
    campeonatos_creados = db.relationship(
        "Campeonato", backref="creador", lazy="dynamic"
    )
    asignaciones = db.relationship(
        "AsignacionJuez",
        foreign_keys="AsignacionJuez.usuario_id",
        backref="usuario",
        lazy="dynamic",
    )
    asignaciones_creadas = db.relationship(
        "AsignacionJuez",
        foreign_keys="AsignacionJuez.asignado_por_id",
        backref="asignado_por",
        lazy="dynamic",
    )
    accesos = db.relationship(
        "AccesoTatami", backref="usuario", lazy="dynamic"
    )
    creado_por = db.relationship(
        "Usuario",
        remote_side=[id],
        foreign_keys=[creado_por_id],
        backref="usuarios_creados",
    )

    def set_password(self, password: str):
        """Hashea y almacena la contraseña."""
        salt = bcrypt.gensalt(BCRYPT_ROUNDS)
        self.password_hash = bcrypt.hashpw(
            password.encode("utf-8"), salt
        ).decode("utf-8")

    def check_password(self, password: str) -> bool:
        """Verifica la contraseña contra el hash almacenado."""
        return bcrypt.checkpw(
            password.encode("utf-8"),
            self.password_hash.encode("utf-8"),
        )

    @staticmethod
    def _club_a_dict(valor) -> dict | None:
        """Un dojang del JSON, en su forma canónica {nombre, ciudad, pais}.

        Acepta también el texto suelto porque la lista nació guardando solo
        nombres, antes de que cada dojang tuviera su propia delegación.
        """
        if isinstance(valor, dict):
            nombre = str(valor.get("nombre") or "").strip()
            ciudad = str(valor.get("ciudad") or "").strip()
            pais = str(valor.get("pais") or "").strip()
        else:
            nombre, ciudad, pais = str(valor or "").strip(), "", ""
        if not nombre:
            return None
        return {"nombre": nombre, "ciudad": ciudad or None, "pais": pais or None}

    @property
    def clubes(self) -> list:
        """Los dojangs del maestro, en orden. El primero es el principal.

        Cada uno con su ciudad y su país. Cuando la columna nueva está vacía se
        arma con `club` + `delegacion` + `pais_delegacion`: así una fila
        guardada antes de que existiera responde lo mismo que respondía.
        """
        if self._clubes:
            return [c for c in map(self._club_a_dict, self._clubes) if c]
        if not self.club:
            return []
        return [{
            "nombre": self.club,
            "ciudad": self.delegacion,
            "pais": self.pais_delegacion,
        }]

    @clubes.setter
    def clubes(self, lista):
        """Fija la lista completa y, con ella, los datos del club principal.

        Es el ÚNICO sitio donde se escriben `club`, `delegacion` y
        `pais_delegacion`: mantenerlos a mano desde cada endpoint es la forma
        segura de que acaben discrepando de la lista.
        """
        limpia = []
        for valor in (lista or []):
            club = self._club_a_dict(valor)
            # Sin repetir: "Dojang Sur" y "DOJANG SUR" son el mismo club, y en
            # la lista del admin saldrían dos veces.
            if club and not any(
                club["nombre"].casefold() == c["nombre"].casefold() for c in limpia
            ):
                limpia.append(club)
        self._clubes = limpia or None
        principal = limpia[0] if limpia else None
        self.club = principal["nombre"] if principal else None
        self.delegacion = principal["ciudad"] if principal else None
        self.pais_delegacion = principal["pais"] if principal else None

    @property
    def nombres_clubes(self) -> list:
        """Solo los nombres, para catálogos y desplegables."""
        return [c["nombre"] for c in self.clubes]

    def dirige_club(self, nombre) -> bool:
        """True si ese club es uno de los suyos (sin distinguir mayúsculas)."""
        return self.club_por_nombre(nombre) is not None

    def club_por_nombre(self, nombre) -> dict | None:
        """El dojang (con su delegación) que se llama así, o None.

        Con esto, lo que se enseña al revisar una inscripción es la delegación
        DEL DOJANG del alumno, no la del maestro: si dirige uno en Cali y otro
        en Popayán, decir siempre "Cali" es sencillamente falso.
        """
        objetivo = str(nombre or "").strip().casefold()
        if not objetivo:
            return None
        for club in self.clubes:
            if club["nombre"].casefold() == objetivo:
                return club
        return None

    @property
    def es_super(self) -> bool:
        """True si es superadmin (la columna puede ser NULL en bases viejas)."""
        return self.rol == "admin" and bool(self.es_superadmin)

    @property
    def es_maestro(self) -> bool:
        return self.rol == "maestro"

    @property
    def puede_ser_juez(self) -> bool:
        """True si el usuario puede asignarse a un tatami: un juez, o un
        maestro con el permiso `puede_juzgar` activado por el admin."""
        return self.rol == "juez" or (self.rol == "maestro" and bool(self.puede_juzgar))

    def necesita_rehash(self) -> bool:
        """True si el hash guardado usa más rondas que las configuradas.

        Permite migrar de forma transparente a un costo menor: tras un login
        correcto, el endpoint vuelve a hashear la contraseña con BCRYPT_ROUNDS,
        así los usuarios creados con 12 rondas pasan a 10 en su próximo ingreso.
        """
        try:
            rondas = int(self.password_hash.split("$")[2])
        except (AttributeError, IndexError, ValueError):
            return True
        return rondas > BCRYPT_ROUNDS

    def to_dict(self, include_asignaciones=False):
        data = {
            "id": self.id,
            "email": self.email,
            "nombre": self.nombre,
            "rol": self.rol,
            "es_superadmin": self.es_super,
            # `club`, `delegacion` y `pais_delegacion` son los del principal y
            # siguen viajando para no romper a nadie que ya los lea; `clubes`
            # es la lista completa, cada dojang con su propia delegación.
            "club": self.club,
            "clubes": self.clubes,
            "delegacion": self.delegacion,
            "pais_delegacion": self.pais_delegacion,
            "puede_juzgar": bool(self.puede_juzgar),
            "activo": self.activo,
            "creado_por_id": self.creado_por_id,
            "creado_por": (
                {
                    "id": self.creado_por.id,
                    "nombre": self.creado_por.nombre,
                    "email": self.creado_por.email,
                }
                if self.creado_por else None
            ),
            "created_at": iso_utc(self.created_at),
            "eliminado_at": iso_utc(self.eliminado_at),
        }
        if include_asignaciones:
            data["asignaciones"] = [
                a.to_dict(include_usuario=False) for a in self.asignaciones.all()
            ]
        return data

    def __repr__(self):
        return f"<Usuario {self.email} ({self.rol})>"
