"""Monthly summary routes — 30-day periods from first activity."""
from datetime import timedelta

from flask import Blueprint, render_template, jsonify
from flask_login import current_user, login_required

from utils.timezone import today_bjt
from models.monthly_summary import MonthlySummary
from agents.monthly_summary_agent import MonthlySummaryAgent

monthly_bp = Blueprint("monthly", __name__, url_prefix="/monthly")

_summary_agent = MonthlySummaryAgent()


@monthly_bp.route("/")
def index():
    user = current_user
    first_date = MonthlySummary.get_first_activity_date(user.id)
    current_period = MonthlySummary.get_period_for_date(first_date, today_bjt())
    return render_template("monthly.html", user=user, current_period=current_period)


@monthly_bp.route("/api/<int:period>")
def get_summary(period):
    user = current_user
    summary = _summary_agent.generate(user, period)
    return jsonify(summary.to_dict())


@monthly_bp.route("/api/list")
def list_summaries():
    user = current_user
    first_date = MonthlySummary.get_first_activity_date(user.id)
    latest_period = MonthlySummary.get_period_for_date(first_date, today_bjt())

    summaries = []
    for p in range(1, latest_period + 1):
        existing = MonthlySummary.query.filter_by(user_id=user.id, period=p).first()
        if existing:
            summaries.append(existing.to_dict())
        else:
            start, end = MonthlySummary.get_period_range(first_date, p)
            summaries.append({
                "period": p,
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
                "label": f"第{p}期 ({start.month}/{start.day} - {(end - timedelta(days=1)).month}/{(end - timedelta(days=1)).day})",
                "title": "",
                "summary_text": "",
                "diary_count": 0,
                "insight_count": 0,
            })

    return jsonify(summaries)


@monthly_bp.route("/api/notifications")
def notifications():
    user = current_user
    first_date = MonthlySummary.get_first_activity_date(user.id)
    latest_period = MonthlySummary.get_period_for_date(first_date, today_bjt())

    profile = user.profile or {}
    last_viewed_period = profile.get("last_viewed_monthly_period", 0)

    new_summaries = []
    for p in range(last_viewed_period + 1, latest_period + 1):
        existing = MonthlySummary.query.filter_by(user_id=user.id, period=p).first()
        if existing and existing.diary_count > 0:
            new_summaries.append({
                "period": p,
                "title": existing.title,
                "label": existing.label,
            })

    return jsonify({"new_summaries": new_summaries, "current_period": latest_period})


@monthly_bp.route("/api/notifications/read", methods=["POST"])
def mark_notifications_read():
    user = current_user
    profile = user.profile or {}
    first_date = MonthlySummary.get_first_activity_date(user.id)
    latest_period = MonthlySummary.get_period_for_date(first_date, today_bjt())
    profile["last_viewed_monthly_period"] = latest_period
    user.profile = profile
    from app import db
    db.session.commit()
    return jsonify({"status": "ok"})
