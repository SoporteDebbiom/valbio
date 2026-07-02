import os
from datetime import timedelta

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DEFAULT_DB = "sqlite:///" + os.path.join(BASE_DIR, "valbio.db")


def _database_uri():
    uri = os.environ.get("DATABASE_URL", DEFAULT_DB)
    # Algunos proveedores entregan la URL antigua "postgres://"; SQLAlchemy
    # necesita "postgresql://".
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    return uri


def _engine_options(uri):
    if uri.startswith("sqlite"):
        # WAL permite lecturas mientras alguien escribe; el timeout evita el
        # error "database is locked" cuando varios usuarios guardan a la vez.
        return {
            "connect_args": {"timeout": 30, "check_same_thread": False},
        }
    # Postgres u otros: reciclar conexiones y verificarlas antes de usarlas.
    return {"pool_pre_ping": True, "pool_recycle": 280}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options(SQLALCHEMY_DATABASE_URI)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_SECURE = os.environ.get("FLASK_ENV") == "production"
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    WTF_CSRF_TIME_LIMIT = None

    BACKUP_DIR = os.environ.get("BACKUP_DIR", os.path.join(BASE_DIR, "backups"))
    BACKUP_INTERVAL_HOURS = int(os.environ.get("BACKUP_INTERVAL_HOURS", "6"))
    BACKUP_KEEP = int(os.environ.get("BACKUP_KEEP", "30"))
    ONLINE_WINDOW_SECONDS = 90

    # Límite de tamaño de subida (importación de Excel).
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    WTF_CSRF_ENABLED = False


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}
