"""
DINAMYT Backend — Entry Point
Ejecutar con: python run.py
"""

import os
from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.extensions import socketio, db

app = create_app()

# Crear tablas y ejecutar seeds al iniciar (solo desarrollo)
with app.app_context():
    db.create_all()
    from app.schema_compat import ensure_optional_columns
    ensure_optional_columns()

    # Seeds automáticos en desarrollo
    if os.getenv("FLASK_ENV") == "development":
        from app.seeds.seed_categorias import seed_categorias
        from app.seeds.seed_admin import seed_admin

        seed_categorias()
        seed_admin(app.config)

# Respaldo automático de la BD local (cada RESPALDO_MINUTOS; 0 = off)
from app.respaldos import iniciar_respaldos
iniciar_respaldos(app)

# La publicación en vivo durante el evento (cada PUBLICAR_MINUTOS; 0 = off).
# Solo hace algo en el PC del evento: con CAMPEONATOS_ONLINE_URL y un paquete
# «para el evento» importado, que es el que trae la llave (app/en_vivo.py).
from app.en_vivo import iniciar_publicacion
iniciar_publicacion(app)


if __name__ == "__main__":
    import logging

    # Silenciar el log por-petición de Werkzeug: con decenas de dispositivos
    # conectados son miles de líneas, y escribir sin parar a la consola de
    # Windows puede llegar a BLOQUEAR el proceso entero (p. ej. si alguien
    # hace clic dentro de la ventana negra y activa "Selección rápida").
    # Solo se muestran advertencias y errores.
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    port = int(os.getenv("PORT", 5000))
    print(f"""
==============================================
     DINAMYT v4 -- BACKEND FLASK
==============================================
  API REST:    http://localhost:{port}
  Socket.IO:   http://localhost:{port}/combate
  Frontend:    {app.config['FRONTEND_URL']}
==============================================
  Ctrl+C para detener
==============================================
""")
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=app.config.get("DEBUG", False),
        use_reloader=False,  # eventlet no soporta reloader
        allow_unsafe_werkzeug=True,
    )
