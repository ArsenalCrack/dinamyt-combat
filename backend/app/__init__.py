"""
DINAMYT Backend — Flask Application Factory
"""

import os
from flask import Flask
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import config_by_name
from .extensions import db, migrate, jwt, cors, socketio


def create_app(config_name=None):
    """Crea y configura la aplicación Flask."""

    load_dotenv()

    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development")

    app = Flask(__name__)
    app.config.from_object(config_by_name.get(config_name, config_by_name["development"]))

    # ── Seguridad: en producción NO se permite arrancar con secretos débiles ──
    SECRETOS_DEBILES = {
        "dinamyt-dev-secret-key",
        "dinamyt-dev-secret-key-2026",
        "dinamyt-dev-secret-key-change-in-production",
        "CAMBIAR-POR-UN-VALOR-ALEATORIO-LARGO",
        "",
        None,
    }
    PASSWORDS_DEBILES = {"Amy2026*", "CAMBIAR-POR-UNA-CONTRASENA-FUERTE", "", None}
    if config_name == "production":
        if app.config.get("JWT_SECRET_KEY") in SECRETOS_DEBILES:
            raise RuntimeError(
                "[SEGURIDAD] JWT_SECRET_KEY usa un valor por defecto o vacío. "
                "Genera uno con: python -c \"import secrets; print(secrets.token_hex(32))\" "
                "y defínelo como variable de entorno antes de desplegar."
            )
        if app.config.get("ADMIN_PASSWORD") in PASSWORDS_DEBILES:
            raise RuntimeError(
                "[SEGURIDAD] ADMIN_PASSWORD usa un valor por defecto o vacío. "
                "Define una contraseña fuerte como variable de entorno antes de desplegar."
            )

    # ── IP real del cliente detrás de un proxy ───────────────────────────────
    # Render termina TLS en su balanceador: sin esto request.remote_addr es la
    # IP del proxy para TODO el mundo, y el límite de 20 intentos por IP pasa a
    # ser un cupo global que un solo atacante agota para todos los demás.
    # Se confía en un número FIJO de saltos: X-Forwarded-For lo puede escribir
    # cualquiera, y leer el extremo equivocado permite falsear la IP a voluntad.
    hops = app.config.get("TRUST_PROXY_HOPS", 0)
    if hops > 0:
        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops, x_port=hops
        )

    # ── Inicializar extensiones ──
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    # FRONTEND_URL acepta varios orígenes separados por coma
    # (ej: "http://192.168.1.50:3000,http://localhost:3000")
    origins = [
        o.strip() for o in str(app.config["FRONTEND_URL"]).split(",") if o.strip()
    ]
    # Despliegue local (LAN sin internet): aceptar cualquier equipo de la red
    # privada en el puerto del frontend, sin tener que fijar la IP del PC a
    # mano. Cubre los tres rangos privados (10.x, 172.16-31.x, 192.168.x) más
    # localhost. El puerto es opcional para no romper si se sirve en otro.
    import re
    lan_regex = re.compile(
        r"^http://("
        r"localhost|127\.0\.0\.1|"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"192\.168\.\d{1,3}\.\d{1,3}|"
        r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
        r")(:\d{2,5})?$"
    )
    cors_origins = origins + [lan_regex]
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": cors_origins}},
        supports_credentials=True,
        # Sin esto el navegador no puede leer el nombre de archivo de las
        # descargas (Content-Disposition) y usa un nombre genérico.
        expose_headers=["Content-Disposition"],
    )
    socketio.init_app(
        app,
        # Red local de confianza: sin restricción de origen para el socket (el
        # JWT viaja en el payload `auth`, no depende de cookies ni del origen).
        cors_allowed_origins="*",
        async_mode=app.config.get("SOCKETIO_ASYNC_MODE", "eventlet"),
        # Heartbeat corto: detecta un corte de WiFi en ~20 s y dispara la
        # reconexión automática del cliente (y el registro local del tatami).
        ping_interval=10,
        ping_timeout=10,
        logger=False,
        engineio_logger=False,
    )

    # ── Importar modelos (para que Alembic los detecte) ──
    from .models import (  # noqa: F401
        ajuste, usuario, campeonato, categoria, tatami, asignacion, combate,
        llave, competidor, resultado_publicado,
    )

    # ── Techo global de peticiones por IP ──
    from .security import registrar_limite_global
    registrar_limite_global(app)

    # ── Contexto de workspace para RLS ──
    registrar_contexto_rls(app)

    # ── Modo mantenimiento ──
    # Va DESPUÉS del contexto de RLS: cuando el superadmin pasa la puerta, la
    # consulta que lo identifica tiene que salir ya con su contexto puesto.
    from .mantenimiento import registrar_modo_mantenimiento
    registrar_modo_mantenimiento(app)

    # ── Registrar Blueprints (API REST) ──
    from .api import register_blueprints
    register_blueprints(app)

    # ── Registrar namespaces Socket.IO ──
    from .sockets import register_socketio_handlers
    register_socketio_handlers(socketio)

    # ── Comandos CLI ──
    register_cli_commands(app)

    return app


def registrar_contexto_rls(app):
    """Fija en cada request el workspace con el que se consultará la BD.

    Va en un `before_request` y no dentro de `@jwt_required()` porque el
    contexto tiene que estar puesto ANTES de la primera consulta del endpoint.
    El token se lee en modo opcional: las rutas públicas no llevan, y ahí el
    contexto queda en acceso total (ver `rls.contexto_de_usuario`).
    """
    from flask_jwt_extended import verify_jwt_in_request
    from .rls import contexto_de_usuario, fijar_contexto

    @app.before_request
    def _contexto_rls():
        usuario = None
        try:
            verify_jwt_in_request(optional=True)
            from .api.scoping import usuario_actual
            usuario = usuario_actual()
        except Exception:
            # Token ausente, caducado o ilegible: se sigue sin contexto. Quien
            # decide si la petición pasa es el @jwt_required() del endpoint,
            # no esto.
            usuario = None
        workspace_id, acceso_total = contexto_de_usuario(usuario)
        fijar_contexto(workspace_id, acceso_total)


def register_cli_commands(app):
    """Registra comandos CLI personalizados."""

    @app.cli.command("seed")
    def seed_command():
        """Ejecuta los seeds de la base de datos."""
        from .seeds.seed_categorias import seed_categorias
        from .seeds.seed_admin import seed_admin

        seed_categorias()
        seed_admin(app.config)
        print("[OK] Seeds ejecutados correctamente.")

    @app.cli.command("reset-admin-password")
    def reset_admin_password_command():
        """Aplica ADMIN_PASSWORD (del .env) al usuario admin existente."""
        from .models.usuario import Usuario

        email = app.config.get("ADMIN_EMAIL", "admin@dinamyt.org")
        password = app.config.get("ADMIN_PASSWORD")
        if not password:
            print("[ERR] ADMIN_PASSWORD no está definida en el entorno.")
            return
        admin = Usuario.query.filter_by(email=email).first()
        if not admin:
            print(f"[ERR] No existe el usuario '{email}'. Ejecuta 'flask seed' primero.")
            return
        admin.set_password(password)
        db.session.commit()
        print(f"[OK] Contraseña de '{email}' actualizada con el valor de ADMIN_PASSWORD.")

    @app.cli.command("rls")
    def rls_command():
        """Crea/actualiza las políticas de RLS y reporta si protegen de verdad."""
        from .rls import ensure_rls, estado_rls

        resultado = ensure_rls()
        if resultado is None:
            print("[--] SQLite: RLS no aplica. El filtro por workspace lo hace la app.")
            return

        aplicadas, fallos = resultado
        if fallos:
            print(f"[ERR] {aplicadas} sentencias aplicadas, {len(fallos)} fallidas:")
            for sentencia, error in fallos:
                print(f"      · {sentencia} -> {error}")
            print(
                "      Si es 'must be owner of table', conéctate con el rol dueño de "
                "las tablas para aplicarlas (una sola vez)."
            )
            return

        ok, motivo = estado_rls()
        print("[OK] Políticas de RLS aplicadas." if ok else f"[ERR] RLS no protege: {motivo}")

    @app.cli.command("init-db")
    def init_db_command():
        """Crea todas las tablas y ejecuta seeds."""
        db.create_all()
        from .schema_compat import ensure_optional_columns
        ensure_optional_columns()
        print("[OK] Tablas creadas.")

        from .rls import ensure_rls
        resultado = ensure_rls()
        if resultado and not resultado[1]:
            print("[OK] Políticas de RLS aplicadas.")

        from .seeds.seed_categorias import seed_categorias
        from .seeds.seed_admin import seed_admin

        seed_categorias()
        seed_admin(app.config)
        print("[OK] Seeds ejecutados correctamente.")
