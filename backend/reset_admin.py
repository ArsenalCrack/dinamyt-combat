from app import create_app, db
from app.models.usuario import Usuario

app = create_app()
with app.app_context():
    admin = Usuario.query.filter_by(email='admin@dinamyt.org').first()
    if admin:
        admin.set_password('Amy2026*')
        db.session.commit()
        print('Password reset successfully')
    else:
        print('Admin not found')
