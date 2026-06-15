"""Analytics routes — data visualization dashboard."""
from datetime import timedelta
from flask import Blueprint, render_template, jsonify
from flask_login import current_user, login_required

from models.analytics import AnalyticsEvent
from models.user import User

analytics_bp = Blueprint("analytics", __name__, url_prefix="/analytics")


@analytics_bp.route("/")
@login_required
def index():
    return render_template("analytics.html", user=current_user)


@analytics_bp.route("/api/stats")
@login_required
def stats():
    """Aggregated analytics data for the dashboard."""
    from app import db
    from sqlalchemy import func
    from utils.timezone import today_bjt

    today = today_bjt()

    event_counts = (db.session.query(
        AnalyticsEvent.event_name,
        func.count(AnalyticsEvent.id),
    ).group_by(AnalyticsEvent.event_name).all())

    # Daily counts for last 14 days
    daily_raw = (db.session.query(
        func.date(AnalyticsEvent.created_at).label("day"),
        func.count(AnalyticsEvent.id),
    ).filter(
        AnalyticsEvent.created_at >= today - timedelta(days=14)
    ).group_by(func.date(AnalyticsEvent.created_at)).order_by(func.date(AnalyticsEvent.created_at)).all())

    daily_labels = []
    daily_counts = []
    for row in daily_raw:
        daily_labels.append(str(row[0])[5:10])  # "2026-06-05" -> "06-05"
        daily_counts.append(row[1])

    causal_count = (db.session.query(func.count(AnalyticsEvent.id))
                    .filter(AnalyticsEvent.event_name == "causal_mention")
                    .filter(AnalyticsEvent.created_at >= today - timedelta(days=7))
                    .scalar() or 0)

    recent = (AnalyticsEvent.query
              .order_by(AnalyticsEvent.created_at.desc())
              .limit(20)
              .all())

    return jsonify({
        "total": AnalyticsEvent.query.count(),
        "event_counts": {name: count for name, count in event_counts},
        "daily": {"labels": daily_labels, "counts": daily_counts},
        "causal_7d": causal_count,
        "recent": [{
            "id": e.id,
            "event": e.event_name,
            "props": e.properties,
            "time": e.created_at.strftime("%m/%d %H:%M") if e.created_at else "",
        } for e in recent],
        "total_users": User.query.count(),
    })


@analytics_bp.route("/api/experiments")
@login_required
def experiment_data():
    """A/B 实验数据 — 按实验名和分组聚合."""
    from app import db
    from sqlalchemy import func
    from sqlalchemy import text

    result = []

    # 所有用户的实验分组
    users = User.query.all()
    experiments_seen = set()

    for u in users:
        if u.experiments:
            for exp_name in u.experiments:
                experiments_seen.add(exp_name)

    from utils.experiments import EXPERIMENTS

    for exp_name in sorted(experiments_seen):
        config = EXPERIMENTS.get(exp_name, {})
        groups_info = {g: {"user_count": 0} for g in config.get("groups", ["control", "treatment"])}

        for u in users:
            group = (u.experiments or {}).get(exp_name, "control")
            if group in groups_info:
                groups_info[group]["user_count"] += 1

        result.append({
            "name": exp_name,
            "description": config.get("description", ""),
            "groups": groups_info,
        })

    return jsonify({"experiments": result})
