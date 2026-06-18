"""Profile routes — user settings and dashboard."""
from flask import Blueprint, render_template, jsonify, request
from flask_login import current_user, login_required

from app import db
from models.user import User
from models.session import Session
from models.insight import Insight
from models.message import Message

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


@profile_bp.route("/api/stats")
def stats():
    user = current_user

    # Counts
    total_sessions = Session.query.filter_by(user_id=user.id).count()
    total_insights = Insight.query.filter_by(user_id=user.id).count()

    # Emotion frequencies — aggregate from all assistant messages in real time
    from collections import Counter
    sessions = Session.query.filter_by(user_id=user.id).all()
    session_ids = [s.id for s in sessions]
    msgs = (Message.query
            .filter(Message.session_id.in_(session_ids))
            .filter(Message.role == "assistant")
            .all())
    all_emotions = []
    for m in msgs:
        meta = m.structured_meta or {}
        all_emotions.extend(meta.get("emotion_tags", []))

    emotion_frequencies = dict(Counter(all_emotions))
    total_emotions = len(all_emotions)

    return jsonify({
        "total_sessions": total_sessions,
        "total_insights": total_insights,
        "total_emotions": total_emotions,
        "emotion_frequencies": emotion_frequencies,
    })


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
