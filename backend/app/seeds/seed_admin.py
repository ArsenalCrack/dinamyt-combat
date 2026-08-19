"""
Seed: Admin inicial
Crea el usuario admin con la contraseña configurada.
"""

from ..extensions import db
from ..models.usuario import Usuario


def seed_admin(config):
    """Crea el usuario admin inicial si no existe."""
    email = config.get("ADMIN_EMAIL", "admin@dinamyt.org")
    password = config.get("ADMIN_PASSWORD") or ""
    nombre = config.get("ADMIN_NOMBRE", "Administrador DINAMYT")

    admin = Usuario.query.filter_by(email=email).first()
    if admin:
        # Idempotente: el admin sembrado es la raíz de la jerarquía. Si la BD
        # viene de una versión sin es_superadmin (columna NULL), se promueve.
        if not admin.es_superadmin:
            admin.es_superadmin = True
            db.session.commit()
            print(f"  [OK] Admin '{email}' promovido a superadmin.")
        else:
            print(f"  [OK] Admin '{email}' ya existe (superadmin).")
        return

    # Sin ADMIN_PASSWORD no se siembra nada. Crear la cuenta con la cadena
    # vacía dejaría un superadmin cuyo hash valida "" como contraseña buena.
    if not password:
        print(
            f"  [ERR] ADMIN_PASSWORD no está definida: no se creó '{email}'. "
            "Defínela en el entorno y vuelve a ejecutar el seed."
        )
        return

    admin = Usuario(
        email=email,
        nombre=nombre,
        rol="admin",
        es_superadmin=True,
        activo=True,
    )
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    print(f"  [OK] Superadmin '{email}' creado con password configurada.")
