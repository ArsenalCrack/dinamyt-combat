"""
DINAMYT Backend — Punto de entrada WSGI para producción.

Render / gunicorn lo usan así (un solo worker, obligatorio):
    gunicorn -k eventlet -w 1 wsgi:app

El estado de los tatamis, los rooms de Socket.IO y el limitador de
intentos viven en la memoria del proceso: NUNCA usar más de 1 worker.
"""
import os

from dotenv import load_dotenv

load_dotenv()

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402

app = create_app(os.getenv("FLASK_ENV", "production"))

# Crear tablas y seeds en el primer arranque (idempotente)
with app.app_context():
    db.create_all()
    from app.schema_compat import ensure_optional_columns
    ensure_optional_columns()

    from app.seeds.seed_categorias import seed_categorias
    from app.seeds.seed_admin import seed_admin
    seed_categorias()
    seed_admin(app.config)

    # Los seeds leen `usuarios` con la sesión del ORM y no siempre cierran su
    # transacción: `seed_admin` sale por la rama SIN commit cuando el admin ya
    # existe y ya es superadmin (seeds/seed_admin.py:24-26). Esa transacción
    # abierta retiene un ACCESS SHARE sobre `usuarios`, y el `ensure_rls()` de
    # abajo pide ACCESS EXCLUSIVE sobre la MISMA tabla desde otra conexión del
    # pool (rls.py, `db.engine.begin()`). La app se bloquea contra sí misma.
    #
    # Cómo se ve cuando pasa, que no se parece a la causa: el ALTER espera hasta
    # que `idle_in_transaction_session_timeout` mata la sesión ociosa; entonces
    # el cierre del contexto revienta al hacer ROLLBACK sobre una conexión
    # muerta, el worker sale con código 3, gunicorn apaga el master («Worker
    # failed to boot») y systemd reinicia. Ciclo infinito, con la página
    # cargando y TODO `/api/` esperando para siempre. Pasó el 29-08-2026.
    #
    # El try/except de abajo NO protege de esto: un bloqueo no es una excepción,
    # y la excepción llega tarde y fuera de su alcance.
    db.session.commit()

    # Red de seguridad por workspace. Se aplica DESPUÉS de los seeds: las
    # políticas filtran por created_by, y sembrar con ellas puestas obligaría a
    # dar contexto a cada seed sin ganar nada (aquí no hay petición de nadie).
    # En SQLite es un no-op; solo hace algo con PostgreSQL.
    #
    # Envuelto en try/except a conciencia: esto es una capa EXTRA, y un fallo
    # aquí no puede impedir que el backend levante. Si el rol de conexión no es
    # dueño de las tablas, los ALTER fallan y sin esta red el proceso moría con
    # status 1 — la app entera caída por una defensa opcional.
    try:
        from app.rls import ensure_rls, estado_rls

        resultado = ensure_rls()
        if resultado is None:
            print("[--] RLS no aplica (SQLite). El filtro por workspace lo hace la app.")
        else:
            aplicadas, fallos = resultado
            if fallos:
                print(
                    f"[SEGURIDAD] RLS incompleto: {aplicadas} sentencias aplicadas, "
                    f"{len(fallos)} fallidas. El aislamiento por workspace SIGUE "
                    "funcionando (lo hace la aplicación); solo falta la red de abajo."
                )
                for sentencia, error in fallos[:3]:
                    print(f"           · {sentencia} -> {error}")
                print(
                    "           Suele ser que el rol de la conexión no es dueño de las "
                    "tablas. Ver la sección de RLS en el README."
                )
            else:
                ok, motivo = estado_rls()
                print("[OK] RLS activo." if ok else f"[SEGURIDAD] RLS no protege: {motivo}")
    except Exception as exc:  # noqa: BLE001 — nunca debe impedir el arranque
        print(f"[SEGURIDAD] No se pudo configurar RLS: {exc}")
        print("           El backend arranca igual; el filtro por workspace no depende de esto.")
