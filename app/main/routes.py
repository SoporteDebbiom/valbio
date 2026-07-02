from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Activity, Project

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
def dashboard():
    q = (request.args.get("q") or "").strip()
    query = Project.query
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(Project.molecule.ilike(like),
                                    Project.code.ilike(like)))
    projects = query.order_by(Project.modified_at.desc()).all()
    return render_template("main/dashboard.html", projects=projects, q=q)


@main_bp.route("/hoja/nueva", methods=["POST"])
@login_required
def new_project():
    p = Project(created_by=current_user.username, modified_by=current_user.username)
    db.session.add(p)
    db.session.commit()
    Activity.record(current_user.username, current_user.role,
                    f"Creó la hoja #{p.id}", "sheet")
    return redirect(url_for("validation.menu", project_id=p.id))


@main_bp.route("/hoja/<int:project_id>/eliminar", methods=["POST"])
@login_required
def delete_project(project_id):
    p = db.get_or_404(Project, project_id)
    label = p.label
    Activity.record(current_user.username, current_user.role,
                    f"Eliminó la hoja «{label}»", "sheet")
    db.session.delete(p)
    db.session.commit()
    flash(f"Hoja «{label}» eliminada.", "success")
    return redirect(url_for("main.dashboard"))
