"""Respaldos de la base de datos en formato JSON.

Funciona igual con SQLite o PostgreSQL porque exporta el contenido de las
tablas, no el archivo. Se puede generar a mano, descargar, restaurar y además
corre solo cada cierto tiempo a medida que la gente trabaja.
"""
import json
import os
from datetime import datetime, timedelta

from app.models import (Activity, ModuleData, Project, SystemState, User,
                        utcnow)
from glob import glob

from flask import current_app

from app.extensions import db

_TS_FMT = "%Y%m%d_%H%M%S"
_LAST_KEY = "last_backup"


def _backup_dir():
    path = current_app.config["BACKUP_DIR"]
    os.makedirs(path, exist_ok=True)
    return path


def snapshot():
    """Arma el diccionario con todo el contenido de la base."""
    users = [{
        "username": u.username,
        "password_hash": u.password_hash,
        "role": u.role,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    } for u in User.query.all()]

    projects = [{
        "id": p.id,
        "molecule": p.molecule,
        "code": p.code,
        "unit": p.unit,
        "decimals": p.decimals,
        "created_by": p.created_by,
        "modified_by": p.modified_by,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "modified_at": p.modified_at.isoformat() if p.modified_at else None,
    } for p in Project.query.all()]

    modules = [{
        "project_id": m.project_id,
        "module": m.module,
        "payload": m.payload,
        "updated_by": m.updated_by,
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    } for m in ModuleData.query.all()]

    activity = [a.as_dict() for a in Activity.query.order_by(Activity.id).all()]

    return {
        "meta": {
            "created_at": utcnow().isoformat(),
            "app": "valbio",
            "counts": {"users": len(users), "projects": len(projects),
                       "modules": len(modules), "activity": len(activity)},
        },
        "users": users,
        "projects": projects,
        "module_data": modules,
        "activity": activity,
    }


def create_backup(reason="manual"):
    """Escribe un archivo de respaldo y devuelve su ruta."""
    data = snapshot()
    name = f"valbio_{utcnow().strftime(_TS_FMT)}.json"
    path = os.path.join(_backup_dir(), name)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    SystemState.set(_LAST_KEY, utcnow().strftime("%Y-%m-%dT%H:%M:%S"))
    _prune()
    return path


def list_backups():
    """Lista los respaldos existentes, del más reciente al más antiguo."""
    out = []
    for path in sorted(glob(os.path.join(_backup_dir(), "valbio_*.json")), reverse=True):
        st = os.stat(path)
        out.append({
            "name": os.path.basename(path),
            "size_kb": round(st.st_size / 1024, 1),
            "modified": datetime.fromtimestamp(st.st_mtime),
        })
    return out


def _prune():
    keep = current_app.config["BACKUP_KEEP"]
    files = sorted(glob(os.path.join(_backup_dir(), "valbio_*.json")), reverse=True)
    for old in files[keep:]:
        try:
            os.remove(old)
        except OSError:
            pass


def restore_backup(data, replace=True):
    """Restaura el contenido de un respaldo. Con replace=True borra los datos
    actuales antes de cargar. Pensado para uso de un administrador."""
    if replace:
        ModuleData.query.delete()
        Project.query.delete()
        Activity.query.delete()
        User.query.delete()
        db.session.commit()
        db.session.expunge_all()

    for u in data.get("users", []):
        if not User.query.filter_by(username=u["username"]).first():
            db.session.add(User(username=u["username"],
                                password_hash=u["password_hash"],
                                role=u.get("role", "Empleado")))
    db.session.commit()

    id_map = {}
    for p in data.get("projects", []):
        proj = Project(molecule=p.get("molecule", ""), code=p.get("code", ""),
                       unit=p.get("unit", "ng/mL"), decimals=p.get("decimals", 4),
                       created_by=p.get("created_by"), modified_by=p.get("modified_by"))
        db.session.add(proj)
        db.session.flush()
        id_map[p["id"]] = proj.id
    db.session.commit()

    for m in data.get("module_data", []):
        pid = id_map.get(m["project_id"])
        if pid:
            db.session.add(ModuleData(project_id=pid, module=m["module"],
                                      payload=m.get("payload", "{}"),
                                      updated_by=m.get("updated_by")))
    db.session.commit()
    return True


def latest_backup_at():
    raw = SystemState.get(_LAST_KEY)
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


def ensure_state():
    """Garantiza la fila de control del último respaldo (para el automático)."""
    if SystemState.get(_LAST_KEY) is None:
        SystemState.set(_LAST_KEY, "1970-01-01T00:00:00")


def maybe_auto_backup():
    """Crea un respaldo si ya pasó el intervalo configurado. Usa una
    actualización condicional para que, con varios procesos, sólo uno lo haga."""
    hours = current_app.config["BACKUP_INTERVAL_HOURS"]
    if hours <= 0:
        return
    cutoff = (utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%S")
    now = utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    claimed = (db.session.query(SystemState)
               .filter(SystemState.key == _LAST_KEY, SystemState.value < cutoff)
               .update({SystemState.value: now}, synchronize_session=False))
    db.session.commit()
    if claimed:
        try:
            data = snapshot()
            name = f"valbio_{utcnow().strftime(_TS_FMT)}.json"
            with open(os.path.join(_backup_dir(), name), "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            _prune()
        except OSError:
            pass
