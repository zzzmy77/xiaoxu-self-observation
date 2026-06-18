"""Insights routes — cross-session analysis."""
import json
from datetime import date
from flask import Blueprint, render_template, jsonify, request
from flask_login import current_user, login_required
from collections import Counter

from models.insight import Insight
from models.message import Message
from models.session import Session
from utils.timezone import today_bjt

insights_bp = Blueprint("insights", __name__, url_prefix="/insights")


@insights_bp.route("/")
@login_required
def index():
    user = current_user
    insights = (Insight.query
                .filter_by(user_id=user.id)
                .order_by(Insight.created_at.desc())
                .all())
    return render_template("insights.html", user=user, insights=insights)


# ── Calendar API ──

@insights_bp.route("/api/calendar")
@login_required
def insight_calendar():
    """Return {date: {has_insight, count}} for a given month."""
    from sqlalchemy import extract
    from app import db

    user = current_user
    _bj = today_bjt()
    year = request.args.get("year", type=int, default=_bj.year)
    month = request.args.get("month", type=int, default=_bj.month)

    insights = (Insight.query
               .filter_by(user_id=user.id)
               .filter(extract("year", Insight.created_at) == year)
               .filter(extract("month", Insight.created_at) == month)
               .all())

    result = {}
    for i in insights:
        if i.created_at:
            key = i.created_at.date().isoformat()
            if key not in result:
                result[key] = {"has_insight": True, "count": 0}
            result[key]["count"] += 1

    return jsonify(result)


@insights_bp.route("/api/day/<int:year>/<int:month>/<int:day>")
@login_required
def insight_day_detail(year, month, day):
    """Return insights for a specific date."""
    from app import db

    user = current_user
    target = date(year, month, day)

    insights = (Insight.query
                .filter_by(user_id=user.id)
                .filter(db.func.date(Insight.created_at) == target)
                .order_by(Insight.created_at.desc())
                .all())

    return jsonify({
        "date": target.isoformat(),
        "insights": [i.to_dict() for i in insights],
    })


@insights_bp.route("/api/data")
def insight_data():
    """Return structured insight data for the dashboard.
    
    Mixes data from the user's cognitive model (10-dimension) and raw message aggregation.
    New fields: core_beliefs, patterns (with evolution), relationships, traits.
    Existing fields preserved for frontend compatibility.
    """
    user = current_user
    cm = user.cognitive_model or {}

    # ── Gather raw message data (kept for attributions and backward compat) ──
    sessions = Session.query.filter_by(user_id=user.id).all()
    session_ids = [s.id for s in sessions]

    msgs = (Message.query
            .filter(Message.session_id.in_(session_ids))
            .filter(Message.role == "assistant")
            .all())

    all_emotions = []
    attribution_list = []
    self_insights = []

    for m in msgs:
        meta = m.structured_meta or {}
        all_emotions.extend(meta.get("emotion_tags", []))
        attr = meta.get("attribution", "")
        if attr and len(attr) > 3:
            attribution_list.append(attr)
        draft = meta.get("insight_draft", "")
        if draft and len(draft) > 10:
            self_insights.append({"text": draft, "date": m.created_at.isoformat() if m.created_at else ""})

    # Emotion frequencies: check profile first (seed factory stores here),
    # then cognitive model, then raw message aggregation
    profile = user.profile or {}
    emotion_freq = profile.get("emotion_frequencies", {})
    if not emotion_freq:
        emotion_freq = cm.get("情绪与心理健康趋势", {})
    if not emotion_freq:
        # Fallback to raw message aggregation
        emotion_freq = dict(Counter(all_emotions))

    # Group attributions (still from raw messages — per-message data)
    attribution_groups = {}
    for a in attribution_list:
        key = a[:20]
        if key not in attribution_groups:
            attribution_groups[key] = {"text": a, "count": 0}
        attribution_groups[key]["count"] += 1

    # ── Pattern Discovery (from message data, kept for backward compat) ──
    legacy_patterns = []
    if len(attribution_list) >= 3:
        stop_words = ["自己", "因为", "然后", "而且", "但是", "觉得", "感觉", "一个", "这个", "那个", "没有", "什么", "怎么"]
        word_counts = {}
        for a in attribution_list:
            for word in a:
                if len(word) >= 2 and word not in stop_words:
                    word_counts[word] = word_counts.get(word, 0) + 1
        common_words = sorted(word_counts.items(), key=lambda x: -x[1])[:5]
        if common_words and common_words[0][1] >= 2:
            top_words = [w for w, c in common_words if c >= 2]
            if top_words:
                legacy_patterns.append(
                    f"🌟 小绪发现：你最近的话题似乎集中在「{'、'.join(top_words[:3])}」——"
                    f"这些关键词在你的归因中出现了{sum(word_counts[w] for w in top_words[:3])}次"
                )

    if len(msgs) >= 6:
        first_half = []
        second_half = []
        half = len(msgs) // 2
        for m in msgs[:half]:
            meta = m.structured_meta or {}
            first_half.extend(meta.get("emotion_tags", []))
        for m in msgs[half:]:
            meta = m.structured_meta or {}
            second_half.extend(meta.get("emotion_tags", []))

        if first_half and second_half:
            fh_top = Counter(first_half).most_common(3)
            sh_top = Counter(second_half).most_common(3)
            fh_set = set(e for e, _ in fh_top)
            sh_set = set(e for e, _ in sh_top)
            new_emotions = sh_set - fh_set
            if new_emotions:
                legacy_patterns.append(
                    f"📈 近期新出现的情绪：{'、'.join(new_emotions)}——和早期对话相比，你的情绪谱在扩展"
                )

    # ── Cognitive Model Data ──

    # Core beliefs with evolution stages
    spirit_evolution = cm.get("精神发展轨迹", {})
    core_beliefs_raw = spirit_evolution.get("core_beliefs", [])
    self_awareness = spirit_evolution.get("self_awareness_evolution", {})
    core_beliefs = []
    for b in core_beliefs_raw:
        core_beliefs.append({
            "belief": b.get("belief", ""),
            "formed_at": b.get("formed_at", ""),
            "confidence": b.get("confidence", 0.5),
        })
    # Add evolution stages from self_awareness
    evolution_stages = []
    if isinstance(self_awareness, dict):
        for stage_key, stage_data in self_awareness.items():
            if isinstance(stage_data, dict) and stage_data.get("description"):
                evolution_stages.append({
                    "stage": stage_key,
                    "description": stage_data["description"],
                    "date": stage_data.get("date", ""),
                })
            elif isinstance(stage_data, str):
                evolution_stages.append({
                    "stage": stage_key,
                    "description": stage_data,
                    "date": "",
                })

    # Pattern library from cognitive model
    pattern_library = cm.get("核心模式库", [])
    patterns_with_evolution = []
    for p in pattern_library:
        patterns_with_evolution.append({
            "pattern": p.get("pattern", ""),
            "first_seen": p.get("first_seen", ""),
            "last_seen": p.get("last_seen", ""),
            "occurrence_count": p.get("occurrence_count", 1),
        })

    # Relationship dynamics
    relationships = cm.get("核心关系网络", {})
    relationship_summary = []
    if isinstance(relationships, dict):
        for rel_name, rel_data in relationships.items():
            relationship_summary.append({
                "name": rel_name,
                "role": rel_data.get("role", "") if isinstance(rel_data, dict) else str(rel_data),
                "impact": rel_data.get("impact", "") if isinstance(rel_data, dict) else "",
            })
    elif isinstance(relationships, list):
        for item in relationships:
            if isinstance(item, dict):
                relationship_summary.append({
                    "name": item.get("name", ""),
                    "role": item.get("role", ""),
                    "impact": item.get("impact", ""),
                })

    # Traits
    personality = cm.get("人格行为与认知特征", {})
    behavioral_traits = personality.get("behavioral", [])
    cognitive_traits = personality.get("cognitive", [])

    # ── Build response ──
    response = {
        # Existing fields (backward compat)
        "emotion_frequencies": emotion_freq,
        "attributions": sorted(attribution_groups.values(), key=lambda x: -x["count"]),
        "self_insights": self_insights[-10:],
        "session_count": len(sessions),
        "total_emotions": len(all_emotions),
        "patterns": legacy_patterns,

        # New fields from cognitive model
        "core_beliefs": core_beliefs,
        "evolution_stages": evolution_stages,
        "pattern_library": patterns_with_evolution,
        "relationships": relationship_summary,
        "traits": {
            "behavioral": behavioral_traits,
            "cognitive": cognitive_traits,
        },
    }

    return jsonify(response)


# ──────────────────────────────────────────────
# Insights V2 API — 洞察页新版数据
# ──────────────────────────────────────────────

EMOTION_COLORS = {
    "焦虑": "#E8A020", "压力": "#D4911A", "委屈": "#B38B5B",
    "愤怒": "#C0392B", "沮丧": "#7F8C8D", "无力": "#95A5A6",
    "开心": "#27AE60", "自豪": "#2980B9", "放松": "#1ABC9C",
    "失落": "#8E44AD", "不安": "#E67E22", "困惑": "#F39C12",
    "绝望": "#C0392B", "悲伤": "#5D6D7E", "自我怀疑": "#AAB7B8",
    "觉察": "#2ECC71", "思考": "#3498DB", "烦躁": "#E67E22",
    "恐惧": "#C0392B", "惊讶": "#9B59B6",
}


def _build_emotion_cloud(emotion_freq: dict) -> dict:
    """将 emotion_freq 转为气泡图数据。"""
    if not emotion_freq:
        return {"bubbles": [], "overall": "neutral"}

    max_count = max(emotion_freq.values()) if emotion_freq else 1
    negative_set = {"焦虑", "压力", "委屈", "愤怒", "沮丧", "无力",
                    "失落", "不安", "悲伤", "自我怀疑", "烦躁", "恐惧"}

    bubbles = []
    pos_total, neg_total = 0, 0

    for emotion, count in sorted(emotion_freq.items(), key=lambda x: -x[1]):
        size = round(count / max_count, 2)
        group = "negative" if emotion in negative_set else "positive"
        color = EMOTION_COLORS.get(emotion, "#888")
        bubbles.append({
            "emotion": emotion,
            "size": max(size, 0.2),  # 最小0.2，太小看不见
            "group": group,
            "color": color,
        })
        if group == "positive":
            pos_total += count
        else:
            neg_total += count

    total = pos_total + neg_total
    if total == 0:
        overall = "neutral"
    elif pos_total / total > 0.6:
        overall = "positive"
    elif neg_total / total > 0.6:
        overall = "negative"
    else:
        overall = "mixed"

    return {"bubbles": bubbles, "overall": overall}


def _get_warm_message(user) -> str:
    """读取缓存的 warm message，没有则返回 None（前端调用 LLM 生成）。"""
    profile = user.profile or {}
    cached = profile.get("last_warm_message", {})
    if cached and isinstance(cached, dict):
        return cached.get("text", "")
    return ""


def _get_pivot_point(user) -> str:
    """读取缓存的转变支点，没有则返回 None。"""
    profile = user.profile or {}
    cached = profile.get("last_pivot_point", {})
    if cached and isinstance(cached, dict):
        return cached.get("text", "")
    return ""


def _build_key_discoveries(user) -> list:
    """从 Insight 表读取关键发现。"""
    insights = (Insight.query
                .filter_by(user_id=user.id)
                .order_by(Insight.created_at.desc())
                .limit(10)
                .all())
    discoveries = []
    for ins in insights:
        if ins.insight_text:
            discoveries.append({
                "date": ins.created_at.strftime("%m/%d") if ins.created_at else "",
                "title": ins.insight_text[:60] + ("..." if len(ins.insight_text) > 60 else ""),
                "detail": ins.insight_text,
                "emotions": ins.emotion_tags or [],
            })
    return discoveries


def _build_cognitive_patterns(cm: dict) -> list:
    """从 cognitive_model 读取认知模式。"""
    patterns = []

    # 从核心模式库读取
    pattern_lib = cm.get("核心模式库", [])
    for p in pattern_lib:
        patterns.append({
            "name": p.get("name", ""),
            "description": p.get("description", ""),
            "occurrence_count": len(p.get("occurrences", [])),
            "first_seen": p.get("discovered_at", ""),
            "triggers": p.get("triggers", [])[:3],
            "evolution": [e.get("stage", "") for e in p.get("evolution", [])],
        })

    # 从精神发展轨迹读取核心信念（提取行为+认知映射）
    beliefs = cm.get("精神发展轨迹", {}).get("core_beliefs", [])
    belief_related = cm.get("人格行为与认知特征", {})
    behavioral = belief_related.get("behavioral", [])
    cognitive = belief_related.get("cognitive", [])

    # 合并：把信念和特质合并为模式卡片
    for b in beliefs:
        b_name = b.get("belief", "")
        if not b_name:
            continue
        # 找匹配的行为特征
        related_behaviors = [
            t.get("trait", "") for t in behavioral
            if any(w in b_name for w in t.get("evidence", "")) or any(
                w in t.get("trait", "") for w in ["评判", "比较", "讨好", "否定"]
            )
        ]
        patterns.append({
            "name": b_name[:20],
            "description": f"核心信念：{b_name}",
            "occurrence_count": len(b.get("milestones", [])),
            "first_seen": b.get("first_noticed", ""),
            "behavior": "、".join(related_behaviors[:2]) if related_behaviors else "",
            "cognition": b.get("root_hypothesis", ""),
            "evolution": [m.get("milestone", "") for m in b.get("milestones", [])],
        })

    return patterns


def _build_stats(user, emotion_freq: dict, session_count: int) -> dict:
    """数据统计（折叠区）。"""
    insights_count = Insight.query.filter_by(user_id=user.id).count()
    return {
        "sessions": session_count,
        "insights": insights_count,
        "top_emotions": dict(sorted(emotion_freq.items(), key=lambda x: -x[1])[:6]),
    }


def _generate_warm_message_llm(user, emotion_freq: dict, discoveries: list) -> str:
    """调 LLM 生成一句温暖的话。"""
    from config import Config
    if not Config.llm_available():
        return ""

    prompt = (
        "你是一个温柔的心理陪伴助手。根据用户的近期情绪数据和关键洞察，"
        "用一句话温暖地总结用户最近的状态。不超过40字，不要评价，只要关心。\n\n"
        f"情绪频率：{dict(list(emotion_freq.items())[:5])}\n"
        f"最近发现：{[d['title'] for d in discoveries[:3]]}\n\n"
        "输出格式：纯文本一句话，例如「最近焦虑比较多，但你也开始觉察了——你在慢慢变化。」"
    )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=Config.LLM_API_KEY, base_url=Config.LLM_BASE_URL)
        resp = client.chat.completions.create(
            model=Config.LLM_MODEL,
            messages=[{"role": "system", "content": prompt}],
            temperature=0.7,
            max_tokens=100,
        )
        text = (resp.choices[0].message.content or "").strip().strip('"').strip("'")
        return text if text else ""
    except Exception:
        return ""


def _generate_pivot_point_llm(user, beliefs: list, discoveries: list) -> str:
    """调 LLM 生成转变支点。"""
    import json
    from config import Config
    if not Config.llm_available():
        return ""

    # 构造对比数据：看核心信念的演化
    belief_evolution = []
    for b in beliefs:
        milestones = b.get("milestones", []) or b.get("evolution", [])
        if milestones:
            belief_evolution.append({
                "name": b.get("belief", "") or b.get("name", ""),
                "milestones": [m.get("milestone", "") or m.get("stage", "") for m in milestones],
            })

    prompt = (
        "你是一个自我成长观察者。用户的认知模型显示以下核心信念的演化过程，"
        "请找出一条'转变的痕迹' —— 同一个主题从负面到正面的变化。\n\n"
        f"信念演化：{json.dumps(belief_evolution, ensure_ascii=False)}\n"
        f"最近洞察：{[d['title'] for d in discoveries[:3]]}\n\n"
        "输出要求：\n"
        "1. 用对比的方式写：'你X次提到...但最近你...'\n"
        "2. 突出用户的进步和力量\n"
        "3. 60-100字\n"
        "4. 纯文本，不要JSON"
    )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=Config.LLM_API_KEY, base_url=Config.LLM_BASE_URL)
        resp = client.chat.completions.create(
            model=Config.LLM_MODEL,
            messages=[{"role": "system", "content": prompt}],
            temperature=0.7,
            max_tokens=200,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return ""


@insights_bp.route("/api/v2")
@login_required
def insight_v2():
    """Insights V2 API — 为洞察页新版前端提供数据。"""
    import json
    from app import db
    from sqlalchemy.orm.attributes import flag_modified

    user = current_user
    cm = user.cognitive_model or {}
    profile = user.profile or {}

    # ── 情绪频率（profile → cognitive_model → 消息聚合）──
    emotion_freq = profile.get("emotion_frequencies", {})
    if not emotion_freq:
        emotion_freq = cm.get("情绪与心理健康趋势", {}).get("recent_trend", {}).get("dominant_emotions", [])
        if emotion_freq:
            # 解析 "焦虑×5" 格式
            parsed = {}
            for item in emotion_freq:
                sep = "×" if "×" in item else "x"
                if sep in item:
                    parts = item.split(sep)
                    parsed[parts[0]] = int(parts[1])
            emotion_freq = parsed
        else:
            emotion_freq = {}

    sessions = Session.query.filter_by(user_id=user.id).count()

    # ── 构建各板块 ──
    emotion_cloud = _build_emotion_cloud(emotion_freq)
    key_discoveries = _build_key_discoveries(user)
    cognitive_patterns = _build_cognitive_patterns(cm)
    stats = _build_stats(user, emotion_freq, sessions)

    # ── 暖言 & 支点：优先读取缓存，没有则后台生成 ──
    warm_message = _get_warm_message(user)
    pivot_point = _get_pivot_point(user)

    should_generate = bool(emotion_freq) and len(key_discoveries) > 0
    generated_warm = False

    if should_generate:
        if not warm_message:
            warm_text = _generate_warm_message_llm(user, emotion_freq, key_discoveries)
            if warm_text:
                profile = dict(user.profile or {})
                profile["last_warm_message"] = {"text": warm_text, "generated_at": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}
                user.profile = profile
                flag_modified(user, 'profile')
                db.session.commit()
                warm_message = warm_text
                generated_warm = True

        if not pivot_point:
            beliefs = cm.get("精神发展轨迹", {}).get("core_beliefs", [])
            pivot_text = _generate_pivot_point_llm(user, beliefs, key_discoveries)
            if pivot_text:
                profile = dict(user.profile or {})
                profile["last_pivot_point"] = {"text": pivot_text, "generated_at": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}
                user.profile = profile
                flag_modified(user, 'profile')
                db.session.commit()
                pivot_point = pivot_text

    # ── mood_headline ──
    overall = emotion_cloud.get("overall", "neutral")
    mood_map = {
        "positive": "你的情绪在向好的方向移动",
        "negative": "最近负面情绪比较多，但觉察本身就是转变的开始",
        "mixed": "你经历着丰富的情绪变化，每一种都在告诉你些什么",
        "neutral": "你的情绪状态比较平稳",
    }
    mood_headline = mood_map.get(overall, "")

    return jsonify({
        "mood_headline": mood_headline,
        "emotion_cloud": emotion_cloud,
        "warm_message": warm_message,
        "key_discoveries": key_discoveries,
        "cognitive_patterns": cognitive_patterns,
        "pivot_point": pivot_point,
        "stats": stats,
    })
