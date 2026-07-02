import json
from datetime import datetime, timedelta, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, login_manager


def utcnow():
    """Marca de tiempo UTC sin zona horaria (compatible con SQLite y Postgres).

    Usa la API recomendada de Python en lugar de datetime.utcnow(), que quedó
    en desuso, pero conserva el mismo valor de siempre (UTC naïve)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="Empleado")
    created_at = db.Column(db.DateTime, default=utcnow)
    last_seen = db.Column(db.DateTime)

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    @property
    def is_admin(self):
        return self.role == "Administrador"

    def online(self, window_seconds=90):
        if not self.last_seen:
            return False
        return utcnow() - self.last_seen < timedelta(seconds=window_seconds)


class Project(db.Model):
    """Hoja de validación. Es un recurso compartido: cualquier usuario
    autenticado puede abrirla y editarla; se guarda quién la creó y quién
    la modificó por última vez."""
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    molecule = db.Column(db.String(120), default="")
    code = db.Column(db.String(120), default="")
    unit = db.Column(db.String(20), default="ng/mL")
    decimals = db.Column(db.Integer, default=4)

    created_by = db.Column(db.String(80))
    modified_by = db.Column(db.String(80))
    created_at = db.Column(db.DateTime, default=utcnow)
    modified_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    modules = db.relationship("ModuleData", backref="project", lazy=True,
                              cascade="all, delete-orphan")

    @property
    def label(self):
        m, c = (self.molecule or "").strip(), (self.code or "").strip()
        if m and c:
            return f"{m} · {c}"
        return m or c or "Hoja sin nombre"

    def touch(self, username):
        self.modified_by = username
        self.modified_at = utcnow()


class ModuleData(db.Model):
    __tablename__ = "module_data"
    __table_args__ = (db.UniqueConstraint("project_id", "module", name="uq_project_module"),)

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    module = db.Column(db.String(40), nullable=False)
    payload = db.Column(db.Text, default="{}")
    updated_by = db.Column(db.String(80))
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    def get_data(self):
        try:
            return json.loads(self.payload or "{}")
        except (ValueError, TypeError):
            return {}

    def set_data(self, data):
        self.payload = json.dumps(data, ensure_ascii=False)

    @property
    def version(self):
        # Marca temporal en milisegundos; el cliente la envía al guardar para
        # detectar si alguien más editó mientras tanto.
        return int(self.updated_at.timestamp() * 1000) if self.updated_at else 0


class Activity(db.Model):
    """Registro de actividad y accesos, visible para todos los usuarios."""
    __tablename__ = "activity"

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=utcnow, index=True)
    username = db.Column(db.String(80))
    role = db.Column(db.String(20))
    category = db.Column(db.String(20), default="general")  # login, sheet, data, user, backup
    action = db.Column(db.String(255))

    @staticmethod
    def record(username, role, action, category="general"):
        db.session.add(Activity(username=username, role=role,
                                action=action, category=category))
        db.session.commit()

    def as_dict(self):
        return {
            "time": self.timestamp.isoformat() + "Z" if self.timestamp else None,
            "user": self.username,
            "role": self.role,
            "category": self.category,
            "action": self.action,
        }


class SystemState(db.Model):
    """Pares clave/valor para el estado interno (p. ej. último respaldo)."""
    __tablename__ = "system_state"

    key = db.Column(db.String(60), primary_key=True)
    value = db.Column(db.String(255))

    @staticmethod
    def get(key, default=None):
        row = db.session.get(SystemState, key)
        return row.value if row else default

    @staticmethod
    def set(key, value):
        row = db.session.get(SystemState, key)
        if row:
            row.value = value
        else:
            db.session.add(SystemState(key=key, value=value))
        db.session.commit()


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
