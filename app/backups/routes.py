import json
import os
import re

from flask import (Blueprint, Response, abort, flash, redirect,
                   render_template, request, send_file, url_for)
from flask_login import current_user

from app.auth.routes import admin_required
from app.backup import (create_backup, latest_backup_at, list_backups,
                        restore_backup, snapshot)
from app.models import Activity, utcnow

backups_bp = Blueprint("backups", __name__)

_NAME_RE = re.compile(r"^valbio_\d{8}_\d{6}\.json$")


def _safe_path(name):
    if not _NAME_RE.match(name or ""):
        abort(404)
    from flask import current_app
    path = os.path.join(current_app.config["BACKUP_DIR"], name)
    if not os.path.isfile(path):
        abort(404)
    return path


@backups_bp.route("/respaldos")
@admin_required
def index():
    return render_template("backups/list.html",
                           backups=list_backups(),
                           last=latest_backup_at())


@backups_bp.route("/respaldos/generar", methods=["POST"])
@admin_required
def generate():
    create_backup(reason="manual")
    Activity.record(current_user.username, current_user.role,
                    "Generó un respaldo", "backup")
    flash("Respaldo generado.", "success")
    return redirect(url_for("backups.index"))


@backups_bp.route("/respaldos/exportar")
@admin_required
def export_now():
    """Descarga un respaldo al instante, sin depender del disco del servidor."""
    data = json.dumps(snapshot(), ensure_ascii=False, indent=2)
    name = f"valbio_{utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    Activity.record(current_user.username, current_user.role,
                    "Descargó un respaldo", "backup")
    return Response(data, mimetype="application/json",
                    headers={"Content-Disposition": f"attachment; filename={name}"})


@backups_bp.route("/respaldos/descargar/<name>")
@admin_required
def download(name):
    return send_file(_safe_path(name), as_attachment=True, download_name=name)


@backups_bp.route("/respaldos/restaurar", methods=["POST"])
@admin_required
def restore():
    name = request.form.get("name", "")
    path = _safe_path(name)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    restore_backup(data, replace=True)
    Activity.record(current_user.username, current_user.role,
                    f"Restauró el respaldo {name}", "backup")
    flash(f"Base restaurada desde {name}.", "success")
    return redirect(url_for("backups.index"))
