"""Analytics routes — internal only, no UI."""
from flask import Blueprint, jsonify, request

from models.analytics import AnalyticsEvent
from models.user import User

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/analytics")
def analytics():
    """Return analytics event summary (dev tool, no user-facing UI)."""
    page = request.args.get("page", 1, type=int)
    per_page = 50
    events = (AnalyticsEvent.query
              .order_by(AnalyticsEvent.created_at.desc())
              .offset((page - 1) * per_page)
              .limit(per_page)
              .all())
    return jsonify({
        "total": AnalyticsEvent.query.count(),
        "page": page,
        "events": [{
            "id": e.id,
            "event": e.event_name,
            "props": e.properties,
            "time": e.created_at.isoformat() if e.created_at else None,
        } for e in events],
    })


@admin_bp.route("/analytics/stats")
def stats():
    """Aggregated stats for quick dev view."""
    from app import db
    from sqlalchemy import func

    event_counts = (db.session.query(
        AnalyticsEvent.event_name,
        func.count(AnalyticsEvent.id),
    ).group_by(AnalyticsEvent.event_name).all())

    return jsonify({
        "events": {name: count for name, count in event_counts},
        "total_events": AnalyticsEvent.query.count(),
        "total_users": User.query.count(),
    })
