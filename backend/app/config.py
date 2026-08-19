import os
from datetime import timedelta

from sqlalchemy.pool import NullPool


class Config:
    """Configuración base de la aplicación."""

    # Base de datos
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "sqlite:///dinamyt.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # El pooler de Supabase/Neon cierra conexiones inactivas; sin esto,
    # la primera petición tras un rato de calma toma una conexión muerta
    # del pool y devuelve 500. pre_ping la verifica antes de usarla.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # JWT
    JWT_SECRET_KEY = os.getenv(
        "JWT_SECRET_KEY", "dinamyt-dev-secret-key"
    )
    # 72 h: cubre un campeonato de fin de semana sin re-login de jueces
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=72)
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"

    # ── Sesión en cookie httpOnly ────────────────────────────────────────────
    # El token deja de vivir en localStorage, donde cualquier script inyectado
    # en la página lo lee entero. Una cookie httpOnly no es visible desde
    # JavaScript: un XSS podrá actuar mientras la pestaña esté abierta, pero no
    # llevarse la sesión para usarla desde otro sitio.
    #
    # Se aceptan las dos ubicaciones: la cookie es la del navegador, y la
    # cabecera sigue viva para las pantallas de tatami y cualquier cliente que
    # no sea un navegador.
    JWT_TOKEN_LOCATION = ["headers", "cookies"]
    JWT_ACCESS_COOKIE_NAME = "dinamyt_session"
    JWT_COOKIE_SAMESITE = os.getenv("COOKIE_SAMESITE", "Lax")
    # `None` obliga a Secure; si no, el navegador descarta la cookie sin avisar.
    JWT_COOKIE_SECURE = (
        os.getenv("COOKIE_SECURE", "").lower() == "true"
        or os.getenv("COOKIE_SAMESITE", "Lax").lower() == "none"
    )
    # La contrapartida de la cookie: viaja sola en cada petición, incluidas las
    # que dispare otra web. Flask-JWT-Extended deja el valor en una cookie que
    # SÍ es legible (csrf_access_token) y exige verlo repetido en la cabecera —
    # el atacante puede provocar el envío, pero no leerlo desde su dominio.
    # Solo se aplica a lo que entra por cookie, no a la cabecera Authorization.
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_CSRF_IN_COOKIES = True
    JWT_ACCESS_CSRF_HEADER_NAME = "X-CSRF-TOKEN"

    # CORS
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

    # Admin inicial. Sin valor por defecto a propósito: una contraseña en el
    # código acaba en el historial de git y en todos los despliegues que la
    # copien. Si falta, el seed avisa y no crea al admin.
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@dinamyt.org")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
    ADMIN_NOMBRE = os.getenv("ADMIN_NOMBRE", "Administrador DINAMYT")

    # Número de proxies de confianza delante de la app (Render pone 1). Con 0
    # se ignora X-Forwarded-For y se usa la IP del socket: es lo correcto en la
    # LAN, donde cualquiera podría falsear la cabecera para saltarse el límite
    # de intentos.
    TRUST_PROXY_HOPS = int(os.getenv("TRUST_PROXY_HOPS", "0") or 0)

    # Flask-SocketIO
    SOCKETIO_ASYNC_MODE = "threading"


class DevelopmentConfig(Config):
    DEBUG = True
    # Despliegue LOCAL (un solo PC sirviendo a la LAN, sin gunicorn):
    # modo "threading" en vez de eventlet. Evita el monkey-patching de eventlet
    # —problemático en Python 3.12+/Windows— y da paralelismo real de hilos para
    # atender a decenas de dispositivos y escribir en la BD sin bloquear el loop.
    SOCKETIO_ASYNC_MODE = "threading"
    # SQLite local: si dos jueces guardan a la vez, esperar el lock hasta 30 s
    # en lugar de fallar con "database is locked".
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "connect_args": {"timeout": 30},
    }


class ProductionConfig(Config):
    DEBUG = False
    SOCKETIO_ASYNC_MODE = "eventlet"
    # Render (y cualquier PaaS con balanceador) termina TLS en su proxy y pone
    # la IP real del cliente en X-Forwarded-For. Sin esto, todas las peticiones
    # llegan con la IP del proxy y el límite por IP se vuelve un cupo global.
    TRUST_PROXY_HOPS = int(os.getenv("TRUST_PROXY_HOPS", "1") or 0)
    # Bajo gunicorn -k eventlet, el QueuePool de SQLAlchemy es inutilizable:
    # eventlet no parchea threading.RLock (no distingue greenlets) y el
    # Condition del pool muere con "cannot notify on un-acquired lock" en
    # cada checkout. NullPool no usa locks ni colas: abre y cierra conexión
    # por petición, y el pooling real lo hace el Session Pooler de Supabase.
    SQLALCHEMY_ENGINE_OPTIONS = {"poolclass": NullPool}


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}
