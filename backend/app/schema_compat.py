"""Compatibilidad ligera de esquema para instalaciones locales sin migraciones."""

from sqlalchemy import inspect, text

from .extensions import db


OPTIONAL_COLUMNS = {
    "usuarios": {
        # Identidad estable entre instancias (local ↔ online). Ver app/uid.py.
        "uid": "VARCHAR(32)",
        # El `sub` de la cuenta del ecosistema (identidad unica, C3).
        "eco_sub": "VARCHAR(64)",
        "creado_por_id": "INTEGER",
        "eliminado_at": "DATETIME",
        # Jerarquía: el superadmin ve todos los workspaces; un admin normal
        # solo ve lo que él creó (sus jueces, campeonatos y competidores).
        "es_superadmin": "BOOLEAN",
        # Rol maestro: club (lo fija el admin) y permiso para juzgar.
        # `clubes` guarda la lista completa cuando dirige varios dojangs; con
        # la columna en NULL el modelo cae a `[club]` (ver models/usuario.py),
        # así que no hace falta rellenarla.
        "club": "VARCHAR(80)",
        "clubes": "JSON",
        "puede_juzgar": "BOOLEAN",
        # Todos los papeles de la persona, y los que la consola le quitó (F2).
        # Con `roles` en NULL el modelo cae a `rol` + `puede_juzgar`, así que
        # tampoco hace falta rellenarla.
        "roles": "JSON",
        "roles_quitados": "JSON",
        # Los que dio el pase, y por eso el pase puede quitar (nº 5, 25 sep 2026).
        # NULL = no consta = no se quita nada: no hace falta rellenarla.
        "roles_del_portal": "JSON",
        # La organización del ecosistema (F4). NULL = no consta: se rellena
        # sola la próxima vez que la persona entra desde el portal.
        "org_id": "VARCHAR(64)",
        "org_nombre": "VARCHAR(150)",
        # Delegación del maestro: ciudad de origen y país derivado.
        "delegacion": "VARCHAR(120)",
        "pais_delegacion": "VARCHAR(80)",
    },
    "asignaciones_juez": {
        "uid": "VARCHAR(32)",
        "asignado_por_id": "INTEGER",
    },
    "tatamis": {
        "uid": "VARCHAR(32)",
    },
    "llaves": {
        "uid": "VARCHAR(32)",
        "tatami_id": "INTEGER",
        "tipo": "VARCHAR(20)",
        "descripcion": "TEXT",
        "estado": "VARCHAR(20)",
        "seccion_clave": "VARCHAR(300)",
    },
    "campeonatos": {
        "config_categorias": "JSON",
        "export_uuid": "VARCHAR(64)",
        # Detalles públicos + ciclo de vida (preparacion/en_curso/finalizado).
        "lugar": "VARCHAR(120)",
        "ciudad": "VARCHAR(120)",
        "pais": "VARCHAR(120)",
        "estado": "VARCHAR(20)",
        # La organización que lo organiza (F4). La rellena `rellenar_org_de_
        # campeonatos` con la de su creador, en cuanto se conoce.
        "org_id": "VARCHAR(64)",
        # «Solo clubes invitados» (25 sep 2026). NULL cuenta como apagado.
        "solo_invitados": "BOOLEAN",
    },
    "competidores": {
        "uid": "VARCHAR(32)",
        # La cuenta de DINAMYT de quien compite con esta ficha (F3). NULL es lo
        # normal: la ficha existe antes que la cuenta, y se reclama después.
        "eco_sub": "VARCHAR(64)",
        "categoria_especial": "BOOLEAN",
        # Fecha de última actualización de datos (peso/cinturón cambian entre
        # campeonatos). NULL en filas viejas = nunca actualizado tras crearse.
        "updated_at": "DATETIME",
    },
    "inscripciones": {
        "uid": "VARCHAR(32)",
        # Moderación de inscripciones enviadas por maestros.
        "estado": "VARCHAR(20)",
        "created_by": "INTEGER",
        "motivo_rechazo": "TEXT",
    },
}

# Valores por defecto para filas creadas ANTES de que existiera la columna
# (se aplican una sola vez, solo donde el valor quedó NULL tras el ALTER).
BACKFILL = {
    # Las inscripciones previas eran todas del admin → participan.
    "inscripciones": {"estado": "aceptada"},
    # Los campeonatos previos arrancan en preparación.
    "campeonatos": {"estado": "preparacion"},
}


# Nombres que se guardan en MAYÚSCULAS (ver `mayusculas` en api/auth.py).
# tabla → columnas. Se normaliza lo que YA estaba guardado: si no, la lista de
# inscritos seguiría mezclando "Juan pérez" con "JUAN PÉREZ" hasta que alguien
# volviera a editar cada ficha a mano.
# Ojo con lo que NO está aquí: `campeonatos.ciudad` y `campeonatos.pais` salen
# del catálogo de `app/geo.py` y se comparan con él por valor exacto — pasarlos
# a mayúsculas los dejaría sin reconocer. La descripción tampoco: ahí cabe una
# frase, no un dato.
COLUMNAS_EN_MAYUSCULAS = {
    "usuarios": ("nombre", "club"),
    "competidores": ("nombre_completo", "club"),
    "asignaciones_juez": ("nombre_display",),
    "campeonatos": ("nombre", "lugar"),
}


def _normalizar_mayusculas(table_names):
    """Sube a mayúsculas los nombres ya guardados. Idempotente.

    Se hace fila a fila desde Python y no con un `UPDATE ... SET x = upper(x)`
    a propósito: el `upper()` de SQLite es SOLO ASCII, así que "josé pérez"
    saldría como "JOSé PéREZ" en el despliegue local. El `str.upper()` de
    Python entiende Unicode y respeta tildes y eñes.

    Solo se tocan las filas que hacen falta, así que en los arranques siguientes
    no escribe nada.
    """
    # Primero se mira el esquema ENTERO y después se escribe. No es cosmética:
    # `inspect(db.engine)` saca su propia conexión del pool y la devuelve con un
    # ROLLBACK — y en SQLite esa es la MISMA conexión que la de la sesión, así
    # que preguntar por las columnas de la segunda tabla deshacía los UPDATE de
    # la primera. Sin error y sin rastro: la migración decía "listo" y los
    # nombres seguían en minúsculas.
    inspector = inspect(db.engine)
    plan = []
    for tabla, columnas in COLUMNAS_EN_MAYUSCULAS.items():
        if tabla not in table_names:
            continue
        existentes = {col["name"] for col in inspector.get_columns(tabla)}
        columnas = [c for c in columnas if c in existentes]
        if columnas:
            plan.append((tabla, columnas))

    total = 0
    for tabla, columnas in plan:
        lista = ", ".join(columnas)
        filas = db.session.execute(
            text(f"SELECT id, {lista} FROM {tabla}")
        ).mappings().all()
        for fila in filas:
            cambios = {
                c: fila[c].upper()
                for c in columnas
                if fila[c] and fila[c] != fila[c].upper()
            }
            if not cambios:
                continue
            asignaciones = ", ".join(f"{c} = :{c}" for c in cambios)
            db.session.execute(
                text(f"UPDATE {tabla} SET {asignaciones} WHERE id = :id"),
                {**cambios, "id": fila["id"]},
            )
            total += 1
    if total:
        db.session.commit()
    return total


def _ensure_usuarios_rol_width(inspector, table_names):
    """Amplía usuarios.rol si una instalación vieja quedó con VARCHAR(5)."""
    if "usuarios" not in table_names:
        return

    columnas = {col["name"]: col for col in inspector.get_columns("usuarios")}
    rol = columnas.get("rol")
    if not rol:
        return

    tipo = rol["type"]
    largo = getattr(tipo, "length", None)
    valores_enum = getattr(tipo, "enums", None)
    necesita_ensanchar = largo is not None and largo < 20
    necesita_salir_de_enum = valores_enum is not None and "maestro" not in valores_enum
    if not necesita_ensanchar and not necesita_salir_de_enum:
        return

    dialecto = db.engine.dialect.name
    if dialecto == "postgresql":
        db.session.execute(
            text("ALTER TABLE usuarios ALTER COLUMN rol TYPE VARCHAR(20) USING rol::text")
        )
    elif dialecto in {"mysql", "mariadb"}:
        db.session.execute(text("ALTER TABLE usuarios MODIFY COLUMN rol VARCHAR(20) NOT NULL"))
    elif dialecto == "sqlite":
        # SQLite no aplica el largo de VARCHAR; dejarlo como está evita reconstruir
        # la tabla y preserva llaves/indices de instalaciones locales antiguas.
        return
    else:
        return

    db.session.commit()


# Columnas cuyo TIPO depende del motor. `eco_sub` es `uuid` en PostgreSQL
# porque así la creó el guion de reconciliación —con su índice único— antes de
# que existiera este código, y dos formas distintas de la misma columna según
# cómo naciera la base es exactamente el tipo de diferencia que se descubre en
# producción. En SQLite (el modo local) no hay tipo `uuid`: queda VARCHAR.
TIPOS_POR_DIALECTO = {
    ("usuarios", "eco_sub"): {"postgresql": "uuid"},
}


def _tipo_de(dialecto, tabla, columna, por_defecto):
    return TIPOS_POR_DIALECTO.get((tabla, columna), {}).get(dialecto, por_defecto)


def ensure_optional_columns():
    """Agrega columnas nuevas cuando la base existente fue creada con una version previa."""
    inspector = inspect(db.engine)
    dialecto = db.engine.dialect.name
    table_names = set(inspector.get_table_names())
    _ensure_usuarios_rol_width(inspector, table_names)

    for table_name, columns in OPTIONAL_COLUMNS.items():
        if table_name not in table_names:
            continue
        existing = {col["name"] for col in inspector.get_columns(table_name)}
        for column_name, column_type in columns.items():
            if column_name in existing:
                continue
            tipo = _tipo_de(dialecto, table_name, column_name, column_type)
            db.session.execute(
                text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {tipo}")
            )
    db.session.commit()

    # Backfill de valores por defecto donde el ALTER dejó NULL (idempotente).
    for table_name, valores in BACKFILL.items():
        if table_name not in table_names:
            continue
        columnas = {col["name"] for col in inspect(db.engine).get_columns(table_name)}
        for column_name, valor in valores.items():
            if column_name not in columnas:
                continue
            db.session.execute(
                text(
                    f"UPDATE {table_name} SET {column_name} = :valor "
                    f"WHERE {column_name} IS NULL"
                ),
                {"valor": valor},
            )
    db.session.commit()

    _ensure_indices_uid(table_names)
    _documento_unico_por_workspace(table_names)

    normalizados = _normalizar_mayusculas(table_names)
    if normalizados:
        print(f"  [OK] Nombres pasados a mayúsculas en {normalizados} registro(s)")

    # F4: los campeonatos sin organización reciben la de su creador, en cuanto
    # se conoce la del creador. Idempotente: en los arranques siguientes solo
    # escribe si alguien entró desde el portal entretanto.
    if {"campeonatos", "usuarios"} <= table_names:
        from .organizacion import rellenar_org_de_campeonatos

        con_org = rellenar_org_de_campeonatos()
        if con_org:
            db.session.commit()
            print(f"  [OK] Organización asignada a {con_org} campeonato(s)")

    # Los uid llevan un valor DISTINTO por fila, así que no salen de un UPDATE
    # plano como el resto: los genera el backfill de app/uid.py.
    from .uid import backfill_uids
    rellenados = backfill_uids()
    if rellenados:
        print(f"  [OK] Identidad de sincronización asignada a {rellenados} registro(s)")


def _documento_unico_por_workspace(table_names):
    """El documento del competidor pasa de único GLOBAL a único por workspace.

    Hasta el 24 de septiembre de 2026 `competidores.documento` se declaraba
    `unique=True, index=True`, y SQLAlchemy lo crea como un ÍNDICE único aparte
    (`ix_competidores_documento`), no como restricción dentro de la tabla. Eso
    es lo que permite cambiarlo aquí sin reconstruir la tabla, también en
    SQLite:

      1. si ese índice es único, se borra y se vuelve a crear sin serlo (sigue
         haciendo falta para buscar por documento);
      2. se crea el único por (created_by, documento).

    El orden importa y no puede fallar: con el global puesto, los datos ya
    cumplen el por-workspace, que es más flojo. Idempotente.

    Por qué: ver el comentario de `documento` en models/competidor.py.
    """
    if "competidores" not in table_names:
        return
    inspector = inspect(db.engine)
    for indice in inspector.get_indexes("competidores"):
        if indice.get("column_names") == ["documento"] and indice.get("unique"):
            nombre = indice["name"]
            db.session.execute(text(f'DROP INDEX IF EXISTS "{nombre}"'))
            db.session.execute(
                text(f'CREATE INDEX IF NOT EXISTS "{nombre}" ON competidores (documento)')
            )
            print("  [OK] El documento del competidor pasa a ser único por workspace")
    # En PostgreSQL el único global podría ser además una RESTRICCIÓN (si la
    # tabla la creó otra herramienta); `get_indexes` no siempre la enseña.
    if db.engine.dialect.name == "postgresql":
        db.session.execute(
            text(
                "ALTER TABLE competidores "
                "DROP CONSTRAINT IF EXISTS competidores_documento_key"
            )
        )
    db.session.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_competidores_workspace_documento "
            "ON competidores (created_by, documento)"
        )
    )
    db.session.commit()


def _ensure_indices_uid(table_names):
    """Índice por uid en las bases que recibieron la columna con ALTER TABLE.

    `db.create_all()` sí crea el índice en una base nueva, pero un ALTER TABLE
    solo agrega la columna. Sin el índice, emparejar por uid al importar haría
    un recorrido completo de la tabla.
    """
    indices = (
        ("usuarios", "uid"),
        ("competidores", "uid"),
        # `/api/mi/*` busca las fichas de una persona por aquí en cada carga.
        ("competidores", "eco_sub"),
        ("tatamis", "uid"),
        ("asignaciones_juez", "uid"),
        ("inscripciones", "uid"),
        ("llaves", "uid"),
        ("campeonatos", "export_uuid"),
        # F4: el informe de administradores y F5 agrupan por organización.
        ("usuarios", "org_id"),
        ("campeonatos", "org_id"),
    )
    for table_name, column_name in indices:
        if table_name not in table_names:
            continue
        # SQLite y PostgreSQL admiten los dos IF NOT EXISTS; el nombre es el
        # mismo que genera SQLAlchemy con index=True, así que no se duplica.
        db.session.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS ix_{table_name}_{column_name} "
                f"ON {table_name} ({column_name})"
            )
        )
    db.session.commit()
