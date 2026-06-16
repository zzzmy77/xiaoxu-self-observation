"""Analytics routes — internal only, no UI."""
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
@login_required
def seed_test_data():
    """为当前用户生成测试数据（内联，避免额外 app context 造成会话错乱）。

    需登录。POST 时带上 ?level=light 指定等级。
    等级: new / light (默认) / medium
    """
    import random
    from datetime import datetime, timezone, timedelta

    level = request.args.get("level", "light")
    user = current_user

    level_turns = {"new": 2, "light": 10, "medium": 30}
    turn_pairs = level_turns.get(level, 10)

    from app import db
    from models.session import Session
    from models.insight import Insight
    from models.diary import Diary
    from models.monthly_summary import MonthlySummary
    from models.message import Message

    # 清除旧数据
    old_sessions = Session.query.filter_by(user_id=user.id).all()
    for s in old_sessions:
        Message.query.filter_by(session_id=s.id).delete()
        Diary.query.filter_by(session_id=s.id).delete()
        Insight.query.filter_by(session_id=s.id).delete()
    Session.query.filter_by(user_id=user.id).delete()
    MonthlySummary.query.filter_by(user_id=user.id).delete()
    db.session.commit()

    # ── 预设场景对话数据 ──
    scenarios = [
        {
            "name": "workplace_injustice",
            "turns": [
                ("user", "今天被老板骂了，明明不是我的错，他都不问清楚就下结论。"),
                ("user", "他在群里@我说报告数据有问题，但我是照旧标准做的。"),
                ("user", "他可以私聊我啊，在群里说真的很没面子。"),
                ("user", "其实这种事不是第一次了，上次也是差不多的方式。"),
                ("user", "算了，想想可能我也有问题，报告写得太简略了。"),
                ("user", "我觉得我在意的是被尊重的方式，而不是批评本身。"),
            ],
            "emotions": ["委屈", "愤怒", "困惑", "沮丧", "觉察"],
            "attributions": ["被冤枉", "标准变更没通知", "被当众批评"],
        },
        {
            "name": "learning_anxiety",
            "turns": [
                ("user", "学不进去，好焦虑，感觉别人都比我进度快。"),
                ("user", "我是不是太慢了，别人已经开始刷题了我还在看书。"),
                ("user", "每次看到别人发的学习打卡我就更焦虑。"),
                ("user", "但我仔细想想好像也没落下什么，就是心态崩了。"),
                ("user", "我应该少看点别人的动态，专注自己的节奏。"),
            ],
            "emotions": ["焦虑", "压力", "觉察", "放松"],
            "attributions": ["和同学对比进度", "害怕落后"],
        },
        {
            "name": "identity_doubt",
            "turns": [
                ("user", "我学滑雪的时候特别开心，因为没人在评判我，我只要去尝试就是好的。"),
                ("user", "但对计算机不一样，我太习惯了用外部标准评判自己的水平。"),
                ("user", "我害怕被外界评判，所以先不断评判自己。这让我很痛苦。"),
                ("user", "我想沉浸式搞好项目，但我害怕方向不对，没有反馈。"),
                ("user", "滑雪每次都有进步感，但做项目不知道该怎么判断方向。"),
                ("user", "所以我把健身和美食加进了生活，不能只看一个点忽略其他。"),
            ],
            "emotions": ["开心", "觉察", "焦虑", "自我怀疑", "放松"],
            "attributions": ["害怕被评判 → 先评判自己", "评判模式跨领域重复"],
        },
    ]

    stage_labels = [
        "能感受到你的感受。愿意多说说吗？",
        "听起来这是一个重要的发现。你感觉这和什么有关？",
        "你以前也有类似的感觉吗？",
        "那你接下来打算怎么做呢？",
    ]
    stage_names = ["empathy", "empathy", "attribution", "attribution", "challenge", "closure"]

    sessions_created = []
    all_emotions = []
    all_attributions = []
    turns_created = 0
    session_idx = 0

    while turns_created < turn_pairs:
        s = Session(user_id=user.id, mode="exploring", active=False, summary={},
                     created_at=datetime.now(timezone.utc) - timedelta(days=session_idx))
        db.session.add(s)
        db.session.commit()

        scene = scenarios[session_idx % len(scenarios)]
        scene_turns = scene["turns"]
        turns_this = min(len(scene_turns), turn_pairs - turns_created)

        session_emotions = []
        session_attributions = []

        for i in range(turns_this):
            turn_i = i % len(scene_turns)
            user_text = scene_turns[turn_i][1]

            # 助手回复
            stage = stage_names[min(i, len(stage_names)-1)]
            emo = random.choice(scene["emotions"])
            attr = random.choice(scene["attributions"]) if stage == "attribution" else ""
            intensity = random.randint(2, 5)
            asst_text = "小绪正在倾听。" + random.choice(stage_labels)

            session_emotions.append(emo)
            if attr:
                session_attributions.append(attr)

            m1 = Message(session_id=s.id, role="user", content=user_text)
            db.session.add(m1)
            m2 = Message(session_id=s.id, role="assistant", content=asst_text,
                         structured_meta={
                             "emotion_tags": [emo],
                             "emotion_intensity": intensity,
                             "stage": stage,
                             "attribution": attr,
                             "absolutist_detected": [],
                             "insight_draft": "",
                         })
            db.session.add(m2)

            all_emotions.append(emo)
            if attr:
                all_attributions.append(attr)
            turns_created += 1

        db.session.commit()

        # Insight
        if session_attributions:
            ins = Insight(
                user_id=user.id, session_id=s.id,
                emotion_tags=list(set(session_emotions)),
                attribution_chain=list(set(session_attributions)),
                insight_text="从今天的对话来看，你发现了" + "、".join(set(session_attributions)) + "。这是值得注意的模式。",
                pattern_hint=scene.get("name", ""),
            )
            db.session.add(ins)

        # Diary
        d = Diary(
            user_id=user.id, session_id=s.id,
            date=(datetime.now(timezone.utc) - timedelta(days=session_idx)).date(),
            title=f"第{session_idx+1}次·{scene['name']}",
            content=f"<p>情绪：{'、'.join(list(set(session_emotions)))}</p>",
            emotion_tags=list(set(session_emotions)),
        )
        db.session.add(d)
        db.session.commit()

        sessions_created.append(s)
        session_idx += 1

    # 更新用户 profile
    import copy
    profile = copy.deepcopy(user.profile) or {}
    emotion_freq = profile.get("emotion_frequencies", {})
    for e in all_emotions:
        emotion_freq[e] = emotion_freq.get(e, 0) + 1
    profile["emotion_frequencies"] = emotion_freq
    profile["common_attributions"] = list(set(all_attributions))
    profile["total_sessions"] = (profile.get("total_sessions", 0) + len(sessions_created))
    user.profile = profile
    db.session.commit()

    # 统计
    stats_sessions = Session.query.filter_by(user_id=user.id).count()
    stats_msgs = Message.query.join(Session).filter(Session.user_id == user.id).count()
    stats_insights = Insight.query.filter_by(user_id=user.id).count()
    stats_diaries = Diary.query.filter_by(user_id=user.id).count()

    return jsonify({
        "status": "ok",
        "level": level,
        "user": user.username,
        "stats": {
            "sessions": stats_sessions,
            "messages": stats_msgs,
            "insights": stats_insights,
            "diaries": stats_diaries,
        }
    })
