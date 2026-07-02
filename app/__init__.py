import os
import secrets
import time

import click
from flask import Flask, render_template, request
from flask_login import current_user

from app.extensions import csrf, db, login_manager
from app.models import User, utcnow
from config import config_by_name

_last_auto_check = 0.0


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    app = Flask(__name__)
    app.config.from_object(config_by_name.get(config_name, config_by_name["development"]))

    _resolve_secret_key(app, config_name)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from app.auth.routes import auth_bp
    from app.backups.routes import backups_bp
    from app.collab.routes import collab_bp
    from app.main.routes import main_bp
    from app.validation.routes import validation_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(validation_bp)
    app.register_blueprint(collab_bp)
    app.register_blueprint(backups_bp)

    _register_hooks(app)
    _register_errors(app)
    _register_cli(app)

    with app.app_context():
        _configure_sqlite()
        db.create_all()
        _ensure_columns()
        if not app.config.get("TESTING"):
            _ensure_admin(app)
            from app.backup import ensure_state
            ensure_state()

    return app


def _resolve_secret_key(app, config_name):
    if app.config.get("SECRET_KEY"):
        return
    if config_name == "production":
        raise RuntimeError(
            "Falta SECRET_KEY. Define la variable de entorno SECRET_KEY antes "
            "de arrancar en producción.")
    # Desarrollo/pruebas: clave efímera en memoria (no se guarda en el código).
    app.config["SECRET_KEY"] = secrets.token_hex(32)


def _register_hooks(app):
    @app.before_request
    def track_presence_and_backup():
        if request.endpoint == "static" or not current_user.is_authenticated:
            return
        now = utcnow()
        if not current_user.last_seen or (now - current_user.last_seen).total_seconds() > 30:
            current_user.last_seen = now
            db.session.commit()
        _auto_backup_if_due(app)

    @app.after_request
    def security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; img-src 'self' data:; object-src 'none'; "
            "base-uri 'self'; frame-ancestors 'none'")
        # HSTS sólo cuando se sirve por HTTPS (producción), nunca en localhost.
        if app.config.get("SESSION_COOKIE_SECURE"):
            resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return resp


def _auto_backup_if_due(app):
    global _last_auto_check
    now = time.time()
    if now - _last_auto_check < 120:
        return
    _last_auto_check = now
    try:
        from app.backup import maybe_auto_backup
        maybe_auto_backup()
    except Exception:
        db.session.rollback()


def _register_errors(app):
    @app.errorhandler(403)
    def forbidden(_):
        return render_template("error.html", code=403,
                               message="No tienes permiso para ver esta página."), 403

    @app.errorhandler(404)
    def not_found(_):
        return render_template("error.html", code=404,
                               message="No encontramos lo que buscabas."), 404

    @app.errorhandler(500)
    def server_error(_):
        db.session.rollback()
        return render_template("error.html", code=500,
                               message="Ocurrió un error en el servidor."), 500


def _register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Crea las tablas y el administrador inicial."""
        _configure_sqlite()
        db.create_all()
        _ensure_columns()
        _ensure_admin(app)
        from app.backup import ensure_state
        ensure_state()
        click.echo("Base de datos lista.")

    @app.cli.command("backup")
    def backup_cmd():
        """Genera un respaldo de toda la base."""
        from app.backup import create_backup
        path = create_backup(reason="cli")
        click.echo(f"Respaldo creado: {path}")

    @app.cli.command("restore")
    @click.argument("path")
    def restore_cmd(path):
        """Restaura la base desde un archivo de respaldo (reemplaza los datos)."""
        import json
        from app.backup import restore_backup
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        restore_backup(data, replace=True)
        click.echo("Restauración terminada.")

    @app.cli.command("list-users")
    def list_users_cmd():
        """Lista los usuarios registrados (no muestra contraseñas)."""
        users = User.query.order_by(User.username).all()
        if not users:
            click.echo("No hay usuarios registrados.")
            return
        for u in users:
            seen = u.last_seen.strftime("%Y-%m-%d %H:%M") if u.last_seen else "nunca"
            click.echo(f"{u.username:20s} {u.role:14s} último acceso: {seen}")

    @app.cli.command("create-admin")
    @click.option("--username", prompt="Usuario")
    @click.password_option()
    def create_admin_cmd(username, password):
        """Crea un administrador. La contraseña se escribe en el momento y nunca
        queda guardada en el código."""
        username = username.strip()
        if User.query.filter_by(username=username).first():
            click.echo(f"El usuario «{username}» ya existe.")
            return
        u = User(username=username, role="Administrador")
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        click.echo(f"Administrador «{username}» creado.")

    @app.cli.command("set-password")
    @click.argument("username")
    @click.password_option()
    def set_password_cmd(username, password):
        """Cambia o restablece la contraseña de un usuario existente."""
        user = User.query.filter_by(username=username.strip()).first()
        if user is None:
            click.echo(f"No existe el usuario «{username}».")
            return
        user.set_password(password)
        db.session.commit()
        click.echo(f"Contraseña actualizada para «{username}».")


def _configure_sqlite():
    uri = db.engine.url
    if uri.get_backend_name() != "sqlite":
        return
    from sqlalchemy import event

    if getattr(db.engine, "_valbio_pragmas", False):
        return
    db.engine._valbio_pragmas = True

    @event.listens_for(db.engine, "connect")
    def _set_pragmas(dbapi_con, _):
        cur = dbapi_con.cursor()
        try:
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.execute("PRAGMA synchronous=NORMAL")
        finally:
            cur.close()


def _ensure_columns():
    """Agrega columnas nuevas a bases ya existentes sin perder datos."""
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    wanted = {
        "users": {"last_seen": "DATETIME"},
        "projects": {"created_by": "VARCHAR(80)", "modified_by": "VARCHAR(80)"},
        "module_data": {"updated_by": "VARCHAR(80)"},
    }
    existing_tables = inspector.get_table_names()
    for table, cols in wanted.items():
        if table not in existing_tables:
            continue
        present = {c["name"] for c in inspector.get_columns(table)}
        for col, ddl in cols.items():
            if col not in present:
                try:
                    db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {col} {ddl}'))
                    db.session.commit()
                except Exception:
                    db.session.rollback()


def _ensure_admin(app):
    if User.query.first() is not None:
        return
    username = os.environ.get("ADMIN_USERNAME", "admin")
    env_pw = os.environ.get("ADMIN_PASSWORD")
    password = env_pw or secrets.token_urlsafe(9)
    admin = User(username=username, role="Administrador")
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    if not env_pw:
        app.logger.warning(
            "Usuario administrador creado: %s. Contraseña temporal: %s "
            "(cámbiala en cuanto inicies sesión).", username, password)
