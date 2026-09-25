"""
API Blueprints Registration
"""


def register_blueprints(app):
    """Registra todos los blueprints de la API."""
    from .auth import auth_bp
    from .campeonatos import campeonatos_bp
    from .tatamis import tatamis_bp
    from .categorias import categorias_bp
    from .combates import combates_bp
    from .reportes import reportes_bp
    from .llaves import llaves_bp
    from .competidores import competidores_bp, inscripciones_bp
    from .resultados import resultados_bp
    from .sincronizacion import sincronizacion_bp
    from .mantenimiento import mantenimiento_bp
    from .mi import mi_bp
    from .subida import subida_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(campeonatos_bp, url_prefix="/api/campeonatos")
    app.register_blueprint(tatamis_bp, url_prefix="/api/tatamis")
    app.register_blueprint(categorias_bp, url_prefix="/api/categorias")
    app.register_blueprint(combates_bp, url_prefix="/api/combates")
    app.register_blueprint(reportes_bp, url_prefix="/api/reportes")
    app.register_blueprint(llaves_bp, url_prefix="/api/llaves")
    app.register_blueprint(competidores_bp, url_prefix="/api/competidores")
    app.register_blueprint(inscripciones_bp, url_prefix="/api/inscripciones")
    app.register_blueprint(resultados_bp, url_prefix="/api/resultados")
    app.register_blueprint(sincronizacion_bp, url_prefix="/api/sincronizacion")
    # Lo de UNA persona: el panel del competidor (F3).
    app.register_blueprint(mi_bp, url_prefix="/api/mi")
    app.register_blueprint(subida_bp, url_prefix="/api/subida")
    # Cuelga de /api a secas: es un interruptor de toda la instalación, no un
    # recurso de ningún módulo (queda en /api/mantenimiento).
    app.register_blueprint(mantenimiento_bp, url_prefix="/api")
