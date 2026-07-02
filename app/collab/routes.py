from datetime import timedelta

from flask import Blueprint, current_app, jsonify, render_template
from flask_login import current_user, login_required

from app.models import Activity, User, utcnow

collab_bp = Blueprint("collab", __name__)


@collab_bp.route("/actividad")
@login_required
def activity():
    entries = Activity.query.order_by(Activity.timestamp.desc()).limit(200).all()
    return render_template("collab/activity.html", entries=entries)


@collab_bp.route("/api/presence")
@login_required
def presence():
    window = current_app.config["ONLINE_WINDOW_SECONDS"]
    cutoff = utcnow() - timedelta(seconds=window)
    online = [{"username": u.username, "role": u.role}
              for u in User.query.filter(User.last_seen >= cutoff)
                                 .order_by(User.username).all()]
    recent = [a.as_dict() for a in
              Activity.query.order_by(Activity.timestamp.desc()).limit(30).all()]
    return jsonify({"you": current_user.username, "online": online, "recent": recent})
