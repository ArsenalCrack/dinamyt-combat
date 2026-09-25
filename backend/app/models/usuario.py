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

# Los roles que da la CONSOLA. `rol` es un String (no Enum de BD) para poder
# ampliar la lista sin migrar el tipo en bases existentes; la validez se
# comprueba en la API. La jerarquía admin>maestro>juez se apoya además en
# `es_superadmin` (booleano aparte) y en `creado_por_id` (workspace).
ROLES_VALIDOS = ("admin", "maestro", "juez")

# ── Los papeles de una persona (F2 y F3 de PLAN-CAMPEONATOS) ────────────────
#
# `PAPELES` son todos los que una persona puede tener A LA VEZ, de más rango a
# menos, y cualquiera puede ser el principal (`rol`).
#
# `competidor` es el único que NO está en `ROLES_VALIDOS`, y ahora es por otra
# razón que en F2. Entonces no había ninguna pantalla para quien solo compite;
# desde F3 la hay (`/mi-panel`) y el espejo de un alumno nace con ese principal.
# Lo que sigue siendo verdad es que **la consola no lo reparte**: crear un
# usuario o cambiarle el rol desde `/admin` sigue ofreciendo solo los tres que
# operan. Competir lo da el pase, o reclamar la ficha.
PAPELES = ("admin", "maestro", "juez", "competidor")


def ordenar_papeles(lista):
    """Sin repetidos ni desconocidos, del de más rango al de menos."""
    vistos = []
    for valor in lista or []:
        papel = str(valor or "").strip()
        if papel in PAPELES and papel not in vistos:
            vistos.append(papel)
    return sorted(vistos, key=PAPELES.index)

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
    # ── Los papeles, en lista (F2 de PLAN-CAMPEONATOS) ──────────────────────
    #
    # `puede_juzgar` es la prueba de que un solo rol ya no daba: cuando un
    # maestro tuvo que puntuar, no se amplió el modelo, se le colgó un booleano
    # al lado. «El admin que compite» o «el juez que además inscribe» serían
    # otras dos columnas así.
    #
    # Mismo patrón que `clubes`, que ya vive en esta tabla: `roles` (JSON) es la
    # lista y la verdad, y **solo su setter escribe `rol` y `puede_juzgar`**:
    #
    #   · `rol` = el principal, el de más rango. Todo lo que ya pregunta por
    #     `rol` —la consola a la que entra, su workspace, las políticas de RLS—
    #     sigue contestando lo mismo.
    #   · `puede_juzgar` = «juzga ADEMÁS de su papel principal», que es lo que
    #     siempre significó. Un juez a secas lo tiene en falso, como hoy.
    #
    # Las filas anteriores tienen `roles` NULL y el getter la arma con esas dos
    # columnas, así que no hace falta ningún backfill.
    #
    # `roles_quitados` son los papeles que quitó la CONSOLA. El pase del
    # ecosistema puede dar papeles, pero no puede devolver uno que alguien quitó
    # aquí a mano: si no, quitarle el de juez a alguien duraría hasta su
    # siguiente inicio de sesión. Ver `fijar_papeles_a_mano`.
    #
    # `roles_del_portal` son los papeles que llegaron POR EL PASE y que la
    # consola no ha hecho suyos (decidido el 25 sep 2026, nº 5 de la PARTE 4).
    # Lo que el portal dio, el portal lo puede quitar: si un pase posterior ya
    # no lo trae, se retira al entrar (`espejo._retirar_lo_que_el_portal_ya_no_da`).
    # Lo puesto a mano aquí no está en esta lista, y `admin` nunca. NULL = no
    # consta de dónde vino = no se quita nada, que es lo prudente para toda
    # fila anterior a esto.
    _roles = db.Column("roles", db.JSON, nullable=True)
    _roles_quitados = db.Column("roles_quitados", db.JSON, nullable=True)
    _roles_del_portal = db.Column("roles_del_portal", db.JSON, nullable=True)
    # ── La organización (F4 de PLAN-CAMPEONATOS) ────────────────────────────
    #
    # El `org_id` del pase: el club o la federación de su pertenencia
    # principal en el ecosistema. Texto y no `uuid`, a propósito: es un dato
    # que se COPIA del pase, no una clave con la que se relacione nada aquí, y
    # `eco_sub` ya enseñó lo que cuesta que la misma columna tenga dos tipos
    # según el motor (ver arriba).
    #
    # Se reescribe en cada entrada desde el portal (`espejo.py`): si la persona
    # cambió de club, esto cambia con ella. NULL es «no consta» —el modo local,
    # los usuarios creados a mano en la consola, quien aún no ha vuelto a
    # entrar— y no es un error.
    #
    # `org_nombre` es solo para enseñarlo («de qué organización es lo que se
    # está viendo», punto 5 de F4). Se pregunta al ecosistema cuando cambia la
    # organización, igual que el club del maestro.
    org_id = db.Column(db.String(64), nullable=True, index=True)
    org_nombre = db.Column(db.String(150), nullable=True)
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

    # ── Papeles ─────────────────────────────────────────────────────────────

    @staticmethod
    def _papeles_de_columnas(rol, puede_juzgar) -> list:
        """Los papeles que dicen `rol` y `puede_juzgar` por sí solos."""
        papeles = [rol] if rol in PAPELES else []
        if rol == "maestro" and puede_juzgar:
            papeles.append("juez")
        return papeles

    @property
    def roles(self) -> list:
        """Todos sus papeles, del de más rango al de menos. El primero es `rol`.

        **Si la lista guardada no cuadra con `rol` y `puede_juzgar`, mandan
        ellas.** Solo pasa si alguien las escribió sin pasar por la lista —un
        guion viejo, un endpoint que no la conoce—, y en ese caso lo que quiso
        decir está en las columnas, no en una lista que ya no se tocó.
        """
        de_columnas = self._papeles_de_columnas(self.rol, self.puede_juzgar)
        guardados = ordenar_papeles(self._roles)
        if not guardados:
            return de_columnas
        juzga_ademas = "juez" in guardados and guardados[0] != "juez"
        if guardados[0] != self.rol or juzga_ademas != bool(self.puede_juzgar):
            return de_columnas
        return guardados

    @roles.setter
    def roles(self, lista):
        """Fija la lista entera y, con ella, `rol` y `puede_juzgar`.

        Es el ÚNICO sitio donde deberían escribirse esas dos columnas: tenerlas
        a mano en cada endpoint es la forma segura de que acaben discrepando.
        """
        limpia = ordenar_papeles(lista)
        if not limpia:
            raise ValueError(
                "Una persona necesita al menos un papel en Campeonatos "
                f"({', '.join(PAPELES)})."
            )
        self._roles = limpia
        self.rol = limpia[0]
        self.puede_juzgar = "juez" in limpia and limpia[0] != "juez"

    def tiene_rol(self, papel) -> bool:
        """True si ese es UNO de sus papeles, sea o no el principal."""
        return papel in self.roles

    @property
    def roles_quitados(self) -> list:
        """Los papeles que la consola le quitó y el pase no puede devolverle."""
        return ordenar_papeles(self._roles_quitados)

    @roles_quitados.setter
    def roles_quitados(self, lista):
        self._roles_quitados = ordenar_papeles(lista) or None

    @property
    def roles_del_portal(self) -> list:
        """Los papeles que dio el pase y que, por eso, el pase puede quitar."""
        return [p for p in ordenar_papeles(self._roles_del_portal) if p != "admin"]

    @roles_del_portal.setter
    def roles_del_portal(self, lista):
        # `admin` nunca: el mando de los campeonatos no lo quita nadie desde fuera.
        self._roles_del_portal = [
            p for p in ordenar_papeles(lista) if p != "admin"
        ] or None

    def fijar_papeles_a_mano(self, nuevos, antes=None):
        """Lo que decide la CONSOLA. Devuelve `(quitados, dados)`.

        Es la otra mitad de «el portal da papeles, solo la consola los quita»
        (D2 del plan): lo que se quita aquí se recuerda en `roles_quitados`,
        para que el pase no lo devuelva al día siguiente; y lo que se vuelve a
        dar aquí se borra de esa lista, porque ya no está quitado.

        Y lo que la consola toca —dar o quitar— deja de ser «del portal»
        (`roles_del_portal`): desde ese momento es una decisión de aquí, y el
        pase ya no lo retira.

        `antes` son los papeles que tenía ANTES de la edición. Hace falta
        pasarlos cuando quien llama ya ha escrito `rol` o `puede_juzgar` por su
        cuenta: en ese momento `self.roles` ya contesta con lo nuevo, y la
        comparación no vería nada quitado.
        """
        antes = list(antes) if antes is not None else self.roles
        self.roles = nuevos
        despues = self.roles
        quitados = [p for p in antes if p not in despues]
        dados = [p for p in despues if p not in antes]
        self.roles_quitados = [
            p for p in self.roles_quitados if p not in dados
        ] + quitados
        self.roles_del_portal = [
            p for p in self.roles_del_portal if p not in dados and p not in quitados
        ]
        return quitados, dados

    @property
    def es_super(self) -> bool:
        """True si es superadmin (la columna puede ser NULL en bases viejas)."""
        return self.rol == "admin" and bool(self.es_superadmin)

    @property
    def es_maestro(self) -> bool:
        return self.rol == "maestro"

    @property
    def puede_ser_juez(self) -> bool:
        """True si el usuario puede asignarse a un tatami: si juez es UNO de
        sus papeles.

        Para toda fila anterior a F2 da exactamente lo mismo que antes —un
        juez, o un maestro con `puede_juzgar`—, porque de ahí sale la lista
        cuando no hay otra.
        """
        return self.tiene_rol("juez")

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
            # Todos sus papeles. `rol` sigue siendo el principal.
            "roles": self.roles,
            # De qué organización del ecosistema es (F4). NULL = no consta.
            "org_id": self.org_id,
            "org_nombre": self.org_nombre,
            # ¿Entra con su cuenta de DINAMYT? Decide si la consola le ofrece
            # poner contraseña (nº 5 de la PARTE 4). El `sub` no sale de aquí.
            "cuenta_de_dinamyt": bool(self.eco_sub),
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
