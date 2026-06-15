"""Diary routes — calendar, listing, CRUD."""
import json
import logging
from datetime import timedelta
from flask import Blueprint, render_template, jsonify, request
from utils.timezone import today_bjt
from flask_login import current_user, login_required

logger = logging.getLogger(__name__)

from app import db
from models.diary import Diary
from models.insight import Insight
from models.session import Session
from agents.diary_agent import DiaryAgent

diaries_bp = Blueprint("diaries", __name__, url_prefix="/diaries")


@diaries_bp.route("/")
@login_required
def index():
    user = current_user
    diaries = Diary.query.filter_by(user_id=user.id).order_by(Diary.date.desc()).all()
    from datetime import date, datetime, timezone, timedelta
    bj_now = datetime.now(timezone.utc) + timedelta(hours=8)
    today = bj_now.date()
    return render_template("diaries.html", user=user, diaries=diaries, today=today)


@diaries_bp.route("/api/calendar")
def calendar_data():
    """Return {date: {has_diary, has_insight, diary_id, insight_id}} for the current month."""
    user = current_user
    _bj = today_bjt()
    year = request.args.get("year", type=int, default=_bj.year)
    month = request.args.get("month", type=int, default=_bj.month)

    # Get diaries for this month
    from sqlalchemy import extract
    diaries = (Diary.query
               .filter_by(user_id=user.id)
               .filter(extract("year", Diary.date) == year)
               .filter(extract("month", Diary.date) == month)
               .all())

    insights = (Insight.query
                .filter_by(user_id=user.id)
                .filter(extract("year", Insight.created_at) == year)
                .filter(extract("month", Insight.created_at) == month)
                .all())

    # Build calendar data
    diary_map = {}
    for d in diaries:
        key = d.date.isoformat()
        diary_map[key] = {"id": d.id, "title": d.title}

    insight_map = {}
    for i in insights:
        key = i.created_at.date().isoformat() if i.created_at else ""
        if key:
            if key not in insight_map:
                insight_map[key] = []
            insight_map[key].append({"id": i.id, "text": i.insight_text[:50]})

    # Return all days with data
    result = {}
    all_keys = set(diary_map.keys()) | set(insight_map.keys())
    for key in all_keys:
        result[key] = {
            "has_diary": key in diary_map,
            "has_insight": key in insight_map,
            "diary": diary_map.get(key),
            "insights": insight_map.get(key, []),
        }

    return jsonify(result)


@diaries_bp.route("/api/day/<year>/<month>/<day>")
def day_detail(year, month, day):
    """Return diaries and insights for a specific date."""
    user = current_user
    target = date(int(year), int(month), int(day))

    diaries = Diary.query.filter_by(user_id=user.id, date=target).all()
    insights = (Insight.query
                .filter_by(user_id=user.id)
                .filter(db.func.date(Insight.created_at) == target)
                .all())

    return jsonify({
        "date": target.isoformat(),
        "diaries": [d.to_dict() for d in diaries],
        "insights": [i.to_dict() for i in insights],
    })


@diaries_bp.route("/api/<int:diary_id>")
def get_diary(diary_id):
    diary = Diary.query.get_or_404(diary_id)
    return jsonify(diary.to_dict())


@diaries_bp.route("/api/<int:diary_id>/update", methods=["POST"])
def update_diary(diary_id):
    diary = Diary.query.get_or_404(diary_id)
    data = request.get_json() or {}
    if "title" in data:
        diary.title = data["title"]
    if "content" in data:
        diary.content = data["content"]
    if "emotion_tags" in data:
        diary.emotion_tags = data["emotion_tags"]
    if "key_events" in data:
        diary.key_events = data["key_events"]
    if "user_reflections" in data:
        diary.user_reflections = data["user_reflections"]
    diary.is_edited = True
    db.session.commit()
    return jsonify({"status": "ok", "diary": diary.to_dict()})


@diaries_bp.route("/api/generate-today", methods=["POST"])
def generate_today():
    """
    Generate or regenerate today's diary manually.
    POST body: { "force": true } to regenerate.
    """
    user = current_user
    data = request.get_json() or {}
    force = data.get("force", False)

    from datetime import datetime, timezone, timedelta
    bj_now = datetime.now(timezone.utc) + timedelta(hours=8)
    today_bj = bj_now.date()

    # Check existing
    existing = Diary.query.filter_by(user_id=user.id, date=today_bj).first()
    if existing and not force:
        return jsonify({
            "status": "exists",
            "message": "今天已有日记，设置 force=true 可重新生成",
            "diary": existing.to_dict(),
        })

    agent = DiaryAgent()
    try:
        diary = agent.generate_or_regenerate(user, today_bj, force=force)
        if diary:
            return jsonify({"status": "ok", "diary": diary.to_dict()})
        else:
            return jsonify({
                "status": "no_data",
                "message": "今天还没有足够的对话数据，先去和小绪聊聊吧",
            }), 400
    except Exception as e:
        logger.error("generate-today error: %s", e)
        return jsonify({"status": "error", "message": str(e)}), 500


@diaries_bp.route("/api/<int:diary_id>/delete", methods=["POST"])
def delete_diary(diary_id):
    """Delete a diary entry."""
    diary = Diary.query.get_or_404(diary_id)
    if diary.user_id != current_user.id:
        return jsonify({"status": "error", "message": "无权删除此日记"}), 403
    db.session.delete(diary)
    db.session.commit()
    return jsonify({"status": "ok", "message": "日记已删除"})
