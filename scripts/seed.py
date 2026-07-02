"""Crea el usuario administrador inicial.

La contraseña se toma de la variable de entorno ADMIN_PASSWORD. Si no está
definida, se genera una aleatoria y se imprime una sola vez. No hay contraseñas
escritas en el código.
"""
import os
import secrets

from app.extensions import db
from app.models import User


def seed_admin():
    username = os.environ.get("ADMIN_USERNAME", "admin")
    if User.query.filter_by(username=username).first():
        print(f"El usuario «{username}» ya existe; nada que hacer.")
        return

    env_pw = os.environ.get("ADMIN_PASSWORD")
    password = env_pw or secrets.token_urlsafe(9)

    user = User(username=username, role="Administrador")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    if env_pw:
        print(f"Administrador «{username}» creado con la contraseña indicada.")
    else:
        print(f"Administrador «{username}» creado. Contraseña temporal: {password}")
        print("Cámbiala en cuanto inicies sesión.")


if __name__ == "__main__":
    from app import create_app

    app = create_app()
    with app.app_context():
        db.create_all()
        seed_admin()
