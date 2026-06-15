"""Insights routes — cross-session analysis."""
from flask import Blueprint, render_template, jsonify
from flask_login import current_user, login_required
from collections import Counter

from models.insight import Insight
from models.message import Message
from models.session import Session

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

    # Emotion frequencies: use cognitive model data when available
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
