from functools import wraps

from flask import (Blueprint, abort, current_app, flash, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required, login_user, logout_user

from app.auth.forms import LoginForm, NewUserForm
from app.extensions import db
from app.models import Activity, User

auth_bp = Blueprint("auth", __name__)


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data.strip()).first()
        if user is None or not user.check_password(form.password.data):
            flash("Usuario o contraseña incorrectos.", "error")
            return render_template("auth/login.html", form=form)
        login_user(user)
        Activity.record(user.username, user.role, "Inició sesión", "login")
        return redirect(request.args.get("next") or url_for("main.dashboard"))

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    Activity.record(current_user.username, current_user.role, "Cerró sesión", "login")
    logout_user()
    return redirect(url_for("auth.login"))


@auth_bp.route("/usuarios", methods=["GET", "POST"])
@admin_required
def users():
    form = NewUserForm()
    if form.validate_on_submit():
        uname = form.username.data.strip()
        if User.query.filter_by(username=uname).first():
            flash(f"El usuario «{uname}» ya existe.", "error")
        else:
            u = User(username=uname, role=form.role.data)
            u.set_password(form.password.data)
            db.session.add(u)
            db.session.commit()
            Activity.record(current_user.username, current_user.role,
                            f"Registró al usuario {uname} ({form.role.data})", "user")
            flash(f"Usuario «{uname}» registrado.", "success")
        return redirect(url_for("auth.users"))

    all_users = User.query.order_by(User.username).all()
    window = current_app.config["ONLINE_WINDOW_SECONDS"]
    return render_template("auth/users.html", form=form, users=all_users, window=window)


@auth_bp.route("/usuarios/<int:user_id>/eliminar", methods=["POST"])
@admin_required
def delete_user(user_id):
    user = db.get_or_404(User, user_id)
    if user.id == current_user.id:
        flash("No puedes eliminar tu propia cuenta.", "error")
        return redirect(url_for("auth.users"))
    # Las hojas son compartidas: al borrar a alguien no se borran sus hojas,
    # sólo se conserva su nombre en el historial.
    Activity.record(current_user.username, current_user.role,
                    f"Eliminó al usuario {user.username}", "user")
    db.session.delete(user)
    db.session.commit()
    flash("Usuario eliminado.", "success")
    return redirect(url_for("auth.users"))
