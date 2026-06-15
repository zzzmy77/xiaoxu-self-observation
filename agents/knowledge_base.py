"""
PersonalKnowledgeBase — Retrieves structured user data for AI context injection.

Updated to read from the 10-dimension 人物认知模型 (cognitive_model)
instead of the flat user.profile.
"""

import logging
from collections import Counter

logger = logging.getLogger(__name__)


class PersonalKnowledgeBase:
    """Personal knowledge base for a single user.

    Three-layer retrieval:
      L1 (SQL, always): cognitive model context
      L2 (SQL, always): recent diary summaries
      L3 (Vector, on-demand): semantic search via KnowledgeStore
    """

    def __init__(self, user, max_chars: int = 1200):
        self.user = user
        self.user_id = user.id
        self.max_chars = max_chars
        self._store = None

    @property
    def store(self):
        if self._store is None:
            from agents.knowledge_store import KnowledgeStore
            self._store = KnowledgeStore(self.user_id)
        return self._store

    # ── L1: Cognitive Model Context ──

    def get_cognitive_context(self) -> str:
        """Build context string from the 10-dimension cognitive model."""
        cm = self.user.cognitive_model or {}
        parts = []

        # 成长背景
        bg = cm.get("成长背景", {})
        impact = bg.get("impact_assessment", "")
        if impact:
            parts.append(f"用户背景：{impact}")

        # 核心信念（活跃的）
        beliefs = cm.get("精神发展轨迹", {}).get("core_beliefs", [])
        active = [b for b in beliefs if b.get("status") in ("正在溯源", "正在松动", "已识别", "活跃")]
        if active:
            belief_lines = ["核心信念："]
            for b in active[:3]:
                milestones = b.get("milestones", [])
                last = milestones[-1].get("milestone", "已识别") if milestones else "已识别"
                belief_lines.append(f"  · «{b['belief']}»（{b.get('status', '追踪中')}）最新：{last}")
            parts.append("\n".join(belief_lines))

        # 核心模式库
        patterns = cm.get("核心模式库", [])
        active_patterns = [p for p in patterns if p.get("status") == "active"]
        if active_patterns:
            pattern_lines = ["识别到的模式："]
            for p in active_patterns[:3]:
                pattern_lines.append(f"  · {p.get('name', '')}（出现{len(p.get('occurrences', []))}次）")
            parts.append("\n".join(pattern_lines))

        # 当前生活状态
        state = cm.get("当前生活状态", {})
        challenges = state.get("challenges", [])
        if challenges:
            parts.append(f"当前压力来源：{'、'.join(challenges[:3])}")

        # 情绪趋势
        emotions = cm.get("情绪与心理健康趋势", {})
        trend = emotions.get("recent_trend", {})
        dom = trend.get("dominant_emotions", [])
        if dom:
            parts.append("近期情绪：" + "、".join(dom[:4]))

        # 人格与认知特征
        traits = cm.get("人格行为与认知特征", {})
        behavioral = [t["trait"] for t in traits.get("behavioral", []) if t.get("stability") == "stable"]
        if behavioral:
            parts.append(f"行为特征：{'、'.join(behavioral[:3])}")
        cognitive = [c["pattern"] for c in traits.get("cognitive", []) if c.get("stability") in ("stable", "observed")]
        if cognitive:
            parts.append(f"思维习惯：{'、'.join(cognitive[:3])}")

        # 关系网络
        relationships = cm.get("核心关系网络", {})
        rel_summary = []
        for name, info in relationships.items():
            charge = info.get("emotional_charge", "")
            rel_summary.append(f"{name}（{charge}）" if charge else name)
        if rel_summary:
            parts.append("核心关系：" + "、".join(list(rel_summary.keys()) if False else rel_summary))

        # 兴趣
        interests = cm.get("兴趣与关注", {})
        recent_focus = interests.get("recent_focus", "")
        if recent_focus:
            parts.append(f"近期关注：{recent_focus}")

        return "\n".join(parts)

    # ── L2: Recent Diary Summaries ──

    def get_recent_diaries(self, limit: int = 3) -> str:
        """Pull recent diary titles and key reflections."""
        from models.diary import Diary
        diaries = (Diary.query
                   .filter_by(user_id=self.user_id)
                   .order_by(Diary.date.desc())
                   .limit(limit)
                   .all())
        if not diaries:
            return ""

        lines = []
        for d in diaries:
            date_str = d.date.isoformat() if d.date else "?"
            item = f"[{date_str}] {d.title}"
            if d.user_reflections:
                reflections = "；".join(r[:40] for r in d.user_reflections[:2])
                item += f" → {reflections}"
            lines.append(item)

        return "📖 近期日记摘要：\n" + "\n".join(lines)

    # ── L3: Recent Insights ──

    def get_recent_insights(self, limit: int = 2) -> str:
        """Pull recent cross-session insights."""
        from models.insight import Insight
        insights = (Insight.query
                    .filter_by(user_id=self.user_id)
                    .order_by(Insight.created_at.desc())
                    .limit(limit)
                    .all())
        if not insights:
            return ""

        lines = []
        for i in insights:
            text = i.insight_text[:120] if i.insight_text else ""
            if text:
                tags = "、".join(i.emotion_tags or [])
                date_str = i.created_at.strftime("%m/%d") if i.created_at else "?"
                lines.append(f"[{date_str}] ({tags}) {text}")

        return "💡 近期洞察：\n" + "\n".join(lines) if lines else ""

    # ── Proactive Message ──

    def get_proactive_message(self) -> str | None:
        """检测是否有活跃模式，返回 AI 开场白。"""
        cm = self.user.cognitive_model or {}
        patterns = cm.get("核心模式库", [])
        active = [p for p in patterns if p.get("status") == "active"]

        if len(active) >= 1:
            top = active[0]
            name = top.get("name", "")
            count = len(top.get("occurrences", []))
            return (
                f"🌱 小绪注意到：你最近有 {count} 次对话都提到了「{name}」。"
                f" 今天想从这个话题开始吗？"
            )

        return None

    # ── Data Level Detection ──

    def get_user_data_level(self) -> int:
        """Return user data maturity level."""
        from models.message import Message
        from models.session import Session

        sessions = Session.query.filter_by(user_id=self.user_id).all()
        if not sessions:
            return 0

        session_ids = [s.id for s in sessions]
        user_msg_count = Message.query.filter(
            Message.session_id.in_(session_ids),
            Message.role == "user",
        ).count()

        if user_msg_count < 5:
            return 0
        elif user_msg_count < 15:
            return 1
        elif user_msg_count < 50:
            return 2
        else:
            return 3

    # ── Quick Checks ──

    @staticmethod
    def _is_casual_chitchat(text: str) -> bool:
        text = text.strip()
        if len(text) < 3:
            return True
        simple = {"嗯", "嗯嗯", "好的", "好吧", "是的", "对啊", "是啊",
                  "没错", "是的呢", "好呀", "行", "可以", "明白了",
                  "懂了", "知道", "谢谢", "感谢", "哈哈", "哈哈哈"}
        return text in simple

    @staticmethod
    def _has_emotion_signal(text: str) -> bool:
        signals = {
            "难过", "开心", "焦虑", "烦", "生气", "无语", "委屈", "愤怒",
            "害怕", "担心", "紧张", "压力", "疲惫", "累", "绝望", "高兴",
            "激动", "感动", "伤心", "痛苦", "郁闷", "烦躁",
            "不安", "慌张", "后悔", "内疚", "惭愧", "失落", "迷茫",
            "无聊", "厌烦", "不满", "不爽",
            "心累", "崩溃", "窒息", "堵", "慌", "空",
            "被批评", "被骂", "老板", "同事", "工作", "学习", "考试",
            "面试", "offer", "分手", "吵架", "朋友", "家人",
            "发现", "意识到", "原来", "为什么", "总是", "从来", "每次",
            "觉得", "以为", "到底", "究竟",
            "忍", "撑", "熬", "扛",
            "不敢", "不会", "不能", "不想",
        }
        for s in signals:
            if s in text:
                return True
        return False

    # ── Builder ──

    def build_context(self, user_input: str = "") -> str:
        """Assemble context: L1 cognitive model + L2 diaries + L3 vector search."""
        level = self.get_user_data_level()

        if level == 0:
            return ""

        sections = []

        # L1: Cognitive model (replaces old get_profile_context)
        cognitive = self.get_cognitive_context()
        if cognitive:
            sections.append(cognitive)

        # L2: Recent diaries
        diaries = self.get_recent_diaries(limit=2)
        if diaries:
            sections.append(diaries)

        # L3: Vector search (on-demand)
        if (level >= 1 and user_input
                and len(user_input.strip()) > 6
                and not self._is_casual_chitchat(user_input)
                and self._has_emotion_signal(user_input)):
            try:
                results = self.store.search(user_input, top_k=3)
                if results:
                    lines = ["📌 相关历史记录："]
                    type_labels = {"diary": "日记", "insight": "洞察", "session": "对话"}
                    for r in results:
                        label = type_labels.get(r["type"], r["type"])
                        lines.append(f"  [{label}] {r['text'][:120]}")
                    sections.append("\n".join(lines))
            except Exception as e:
                logger.warning(f"L3 vector search failed: {e}")

        result = "\n\n".join(sections)
        if len(result) > self.max_chars:
            result = result[:self.max_chars - 20] + "..."
        return result

    def build_system_context_block(self, mode: str = "exploring",
                                   user_input: str = "") -> str:
        """Build the full context block for system prompt injection."""
        context = self.build_context(user_input=user_input)
        if not context:
            return ""
        return (
            "\n\n【私人知识库 — 该用户的历史参考信息】\n"
            + context
            + "\n【私人知识库结束】\n"
            + "使用方式：公共知识 + 私人知识配合回答。"
            + "私人知识中不相关的信息不要强行引用，始终优先响应用户的当前输入。"
        )
