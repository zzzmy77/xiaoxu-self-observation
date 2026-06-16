"""MemoryAgent: stores conversation data and updates the cognitive model.

After each exploring-mode conversation, extracts structured information
from the dialogue and updates the user's 10-dimension cognitive model.
"""
import logging
from datetime import datetime, timezone
from agent_framework.base import BaseAgent
from models.user import User

logger = logging.getLogger(__name__)


class MemoryAgent(BaseAgent):
    """Saves each turn to DB and updates user's cognitive model."""
    name = "memory"

    def __init__(self):
        super().__init__()
        self.system_prompt = ""

    # ── Emotional signal keywords ──
    _LIFE_EVENT_KEYWORDS = [
        "离职", "入职", "辞职", "换工作", "毕业", "搬家", "分手",
        "在一起", "结婚", "确诊", "住院", "手术", "去世", "考试",
        "上岸", "面试", "offer", "实习", "转正",
    ]
    _RELATIONSHIP_FIGURES = {
        "妈妈": "母亲", "妈": "母亲", "母亲": "母亲",
        "爸爸": "父亲", "爸": "父亲", "父亲": "父亲",
        "男票": "男朋友", "男友": "男朋友", "男朋友": "男朋友",
        "女票": "女朋友", "女友": "女朋友", "女朋友": "女朋友",
        "对象": "伴侣", "老公": "伴侣", "老婆": "伴侣",
        "奶奶": "奶奶", "爷爷": "爷爷",
        "闺蜜": "朋友", "朋友": "朋友", "同事": "同事",
    }
    _LIFE_CHANGE_KEYWORDS = [
        "适应", "压力", "累", "忙", "焦虑", "开心", "顺利",
        "不顺利", "新", "刚开始", "还不熟",
    ]
    _COGNITIVE_PATTERNS = {
        "灾难化": ["完了", "没救了", "最坏的", "肯定不行"],
        "过度归因": ["都是我的错", "怪我", "我不该"],
        "非黑即白": ["要么", "必须", "完美", "绝对不能"],
        "读心": ["他们一定觉得", "他肯定认为", "别人会觉得"],
        "情绪推理": ["感觉很糟糕所以肯定很糟糕"],
    }
    _BELIEF_TRIGGER_WORDS = {
        "我需要讨好别人": ["讨好", "让别人满意", "怕别人不高兴", "先让别人"],
        "被否定 = 我很差": ["被批评", "被否定", "被说", "被骂", "指责"],
        "我不能示弱": ["自己扛", "不麻烦别人", "撑住", "忍住"],
        "我不配被爱": ["不配", "不值得", "我不好", "不够好"],
    }

    def run(self, context: dict, save_messages: bool = True) -> dict:
        session = context.get("session")
        user = context.get("user")
        user_input = context.get("user_input", "")
        response_text = context.get("response_text", "")
        meta = context.get("structured_meta", {})
        mode = session.mode if session else "exploring"

        if not session or not user:
            return context

        try:
            # Save messages (streaming path already saves them separately)
            if save_messages:
                session.add_message(role="user", content=user_input)
                session.add_message(role="assistant", content=response_text, structured_meta=meta)

            # Update cognitive model after exploring mode conversations
            if mode == "exploring":
                self._update_cognitive_model(user, session, meta, response_text)

        except Exception as e:
            logger.error("MemoryAgent error: %s", e)

        return context

    # ════════════════════════════════════════════════════
    #  Cognitive Model Update
    # ════════════════════════════════════════════════════

    def _update_cognitive_model(self, user, session, meta, response_text):
        """Update the 10-dimension cognitive model from conversation data."""
        cm = user.cognitive_model
        if not cm or not isinstance(cm, dict):
            cm = User.default_cognitive_model()
        else:
            # Force a copy to ensure SQLAlchemy detects the change on commit
            cm = dict(cm)

        session_date = session.created_at.strftime("%m%d") if session.created_at else ""

        # ── D6: 情绪趋势 ──
        self._update_emotion_trend(cm, meta, session_date)

        # ── D5: 精神发展（核心信念匹配） ──
        self._update_beliefs(cm, meta, session_date)

        # ── D4: 核心关系 ──
        self._update_relationships(cm, response_text, session_date)

        # ── D3: 人生经历 ──
        self._update_life_events(cm, response_text, session_date)

        # ── D7: 当前生活状态 ──
        self._update_life_state(cm, meta, response_text)

        # ── D8: 认知特征 ──
        self._update_cognitive_patterns(cm, response_text)

        user.cognitive_model = cm
        from app import db
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(user, '_cognitive_model_raw')
        db.session.commit()

    # ─── D6: 情绪趋势 ───

    def _update_emotion_trend(self, cm, meta, session_date):
        emotions = cm.setdefault("情绪与心理健康趋势", {})
        trend = emotions.setdefault("recent_trend", {})
        dom = trend.setdefault("dominant_emotions", [])

        for tag in meta.get("emotion_tags", []):
            found = False
            for i, item in enumerate(dom):
                # Split on either x or x
                sep = "\u00d7"
                if sep not in item:
                    sep = "x"
                if sep not in item:
                    continue
                parts = item.split(sep)
                existing_tag = parts[0]
                if existing_tag == tag:
                    count = int(parts[1]) + 1
                    dom[i] = f"{tag}\u00d7{count}"
                    found = True
                    break
            if not found:
                dom.append(f"{tag}\u00d71")

        # Keep top 10, sort by count desc
        def _extract_count(item):
            sep = "\u00d7" if "\u00d7" in item else "x"
            return int(item.split(sep)[1]) if sep in item else 0
        dom.sort(key=lambda x: -_extract_count(x))
        trend["dominant_emotions"] = dom[:10]

    # ─── D5: 精神发展 —— 核心信念匹配 ───

    def _update_beliefs(self, cm, meta, session_date):
        attribution = meta.get("attribution", "")
        if not attribution or len(attribution) < 4:
            return

        beliefs = (cm.setdefault("精神发展轨迹", {})
                     .setdefault("core_beliefs", []))

        matched = self._match_belief(attribution, beliefs)
        if matched:
            # Update existing belief - add milestone
            milestones = matched.setdefault("milestones", [])
            # Avoid duplicate milestones within same date
            if not milestones or milestones[-1].get("date") != session_date:
                milestones.append({
                    "date": session_date,
                    "milestone": "再次触发",
                    "quote": attribution[:60]
                })
        else:
            # Check if this attribution matches a belief trigger word
            for belief_name, triggers in self._BELIEF_TRIGGER_WORDS.items():
                for t in triggers:
                    if t in attribution:
                        # New belief discovered
                        beliefs.append({
                            "belief": belief_name,
                            "status": "已识别",
                            "first_noticed": session_date,
                            "root_hypothesis": "",
                            "confidence": 0.3,
                            "milestones": [{
                                "date": session_date,
                                "milestone": "首次发现",
                                "quote": attribution[:60]
                            }],
                            "triggers": triggers[:3],
                            "related_patterns": [],
                        })
                        break
                else:
                    continue
                break

    def _match_belief(self, attribution, beliefs):
        for b in beliefs:
            triggers = b.get("triggers", [])
            for t in triggers:
                if t in attribution:
                    return b
            name = b.get("belief", "")
            if name and name[:4] in attribution:
                return b
        return None

    # ─── D4: 核心关系网络 ───

    def _update_relationships(self, cm, response_text, session_date):
        if not response_text or len(response_text) < 5:
            return

        relationships = cm.setdefault("核心关系网络", {})
        for keyword, role in self._RELATIONSHIP_FIGURES.items():
            if keyword in response_text:
                if role not in relationships:
                    relationships[role] = {
                        "role": role,
                        "current_status": "存在但未深入了解",
                        "emotional_charge": "",
                        "evolution": [],
                        "related_patterns": [],
                    }
                # Update evolution if not duplicate
                evo = relationships[role].setdefault("evolution", [])
                if not evo or evo[-1].get("date") != session_date:
                    evo.append({
                        "date": session_date,
                        "observation": f"用户提到了「{role}」",
                        "context": response_text[:40],
                    })

    # ─── D3: 人生经历 ───

    def _update_life_events(self, cm, response_text, session_date):
        if not response_text:
            return
        timeline = cm.setdefault("人生经历时间线", [])
        for keyword in self._LIFE_EVENT_KEYWORDS:
            if keyword in response_text:
                # Only add if not duplicate
                event_text = f"{session_date}: 涉及「{keyword}」"
                existing = any(e.get("event", "").endswith(f"「{keyword}」") for e in timeline[-5:])
                if not existing:
                    timeline.append({
                        "date": session_date,
                        "event": event_text,
                        "type": self._classify_event(keyword),
                        "impact": "unknown",
                    })
                break

    @staticmethod
    def _classify_event(keyword):
        if keyword in ("离职", "入职", "辞职", "换工作", "面试", "offer", "转正"):
            return "职场"
        if keyword in ("分手", "在一起", "结婚"):
            return "亲密关系"
        if keyword in ("确诊", "住院", "手术", "去世"):
            return "健康"
        if keyword in ("毕业", "考试", "上岸"):
            return "学业"
        if keyword in ("搬家",):
            return "生活"
        return "其他"

    # ─── D7: 当前生活状态 ───

    def _update_life_state(self, cm, meta, response_text):
        state = cm.setdefault("当前生活状态", {})
        challenges = state.setdefault("challenges", [])
        strengths = state.setdefault("strengths", [])

        # Detect emotions as challenges if intensity > 3
        intensity = meta.get("emotion_intensity", 0)
        for tag in meta.get("emotion_tags", []):
            negative = tag in ("焦虑", "委屈", "愤怒", "害怕", "担心", "压力", "累", "烦躁")
            if negative and intensity >= 3:
                challenge = f"{tag}（强度{intensity}）"
                if challenge not in challenges:
                    challenges.append(challenge)

        # Detect strengths from positive signals
        if meta.get("stage") in ("closure", "challenge") and meta.get("attribution"):
            strength = "有自我反思意愿"
            if strength not in strengths:
                strengths.append(strength)

        # Keep manageable size
        state["challenges"] = challenges[-5:]
        state["strengths"] = strengths[-3:]

    # ─── D8: 认知特征 ───

    def _update_cognitive_patterns(self, cm, response_text):
        traits = cm.setdefault("人格行为与认知特征", {})
        cognitive = traits.setdefault("cognitive", [])

        existing_patterns = {c["pattern"] for c in cognitive}
        for pattern_name, keywords in self._COGNITIVE_PATTERNS.items():
            for kw in keywords:
                if kw in response_text:
                    if pattern_name not in existing_patterns:
                        cognitive.append({
                            "pattern": pattern_name,
                            "evidence": f"用户说过「{kw}」",
                            "stability": "observed",
                            "note": "",
                        })
                        existing_patterns.add(pattern_name)
                    break
