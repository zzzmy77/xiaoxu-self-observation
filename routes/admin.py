"""Analytics routes — internal only, no UI."""
import sys, os
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

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


@admin_bp.route("/seed-tool")
@login_required
def seed_tool():
    """测试数据工具页面。"""
    from flask import render_template
    return render_template("seed_tool.html", user=current_user)


@admin_bp.route("/seed", methods=["POST"])
def seed_test_data():
    """为当前 demo 用户生成测试数据。

    生产环境调试工具，POST 时带上 ?level=light 指定等级。
    等级: new / light (默认) / medium

    用法:
        curl -X POST https://your-app.railway.app/admin/seed?level=medium
    """
    level = request.args.get("level", "light")

    # 只在生产环境或非 debug 模式下限制访问
    from flask import current_app
    if not current_app.debug and request.headers.get("X-Seed-Key") != "xiaoxu-dev-tool":
        return jsonify({"error": "需要 X-Seed-Key 头或 DEBUG 模式"}), 403

    user = User.get_or_create_default()

    from app import db
    # 清除旧数据
    from models.session import Session
    from models.insight import Insight
    from models.diary import Diary
    from models.monthly_summary import MonthlySummary
    from models.message import Message
    
    old_sessions = Session.query.filter_by(user_id=user.id).all()
    for s in old_sessions:
        Message.query.filter_by(session_id=s.id).delete()
        Diary.query.filter_by(session_id=s.id).delete()
        Insight.query.filter_by(session_id=s.id).delete()
    Session.query.filter_by(user_id=user.id).delete()
    MonthlySummary.query.filter_by(user_id=user.id).delete()
    db.session.commit()

    # 用 Seed Factory 生成数据
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from tests.seed_factory import SeedFactory
    factory = SeedFactory(current_app)
    factory.create_user_for_level(user.username, level)
    factory.close()

    # 统计
    sessions = Session.query.filter_by(user_id=user.id).count()
    insights = Insight.query.filter_by(user_id=user.id).count()
    diaries = Diary.query.filter_by(user_id=user.id).count()
    msg_count = Message.query.join(Session).filter(Session.user_id == user.id).count()

    return jsonify({
        "status": "ok",
        "level": level,
        "user": user.username,
        "stats": {
            "sessions": sessions,
            "messages": msg_count,
            "insights": insights,
            "diaries": diaries,
        }
    })
