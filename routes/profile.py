"""Profile routes — user settings and dashboard."""
from flask import Blueprint, render_template, jsonify, request
from flask_login import current_user, login_required

from app import db
from models.user import User

profile_bp = Blueprint("profile", __name__, url_prefix="/profile")



@profile_bp.route("/")
@login_required
def index():
    user = current_user
    return render_template("profile.html", user=user, identity_options=User.IDENTITY_OPTIONS)


@profile_bp.route("/api")
def api():
    user = current_user
    return jsonify(user.to_dict())


@profile_bp.route("/api/update", methods=["POST"])
def update():
    user = current_user
    data = request.get_json() or {}

    # Update settings
    settings = user.settings or {}
    if "mode" in data:
        settings["mode"] = data["mode"]
    user.settings = settings

    # Update profile fields (identity, status, industry, profession)
    profile = user.profile or {}
    for field in ("identity", "status", "industry", "profession"):
        if field in data:
            profile[field] = data[field]
    if "username" in data:
        user.username = data["username"]

    user.profile = profile
    db.session.commit()
    return jsonify({"status": "ok", "profile": profile, "settings": settings})
