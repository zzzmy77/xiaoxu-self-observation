"""DiaryAgent: generates a diary entry from a completed conversation."""
import json
import logging
import os
from datetime import date
from openai import OpenAI

from agent_framework.base import BaseAgent
from models.diary import Diary
from models.insight import Insight
from config import Config

logger = logging.getLogger(__name__)

DIARY_SYSTEM_PROMPT = """你是一个温暖、细腻的日记撰写助手。
你将用户的对话记录转化为一篇有温度的日记。

请基于以下对话消息和结构化数据，生成一段日记。

日记格式（纯JSON，不要多余文字）：
{
  "title": "6月5日·工作压力的觉察",
  "content": "<p>今天我和小绪聊到了工作中的烦恼……</p><p>我发现……</p>",
  "key_events": ["被老板当众批评报告数据问题"],
  "user_reflections": ["发现自己难受的不是批评本身，而是被对待的方式"]
}

要求：
- title: 日期前缀 + 主题，不超过20字
- content: HTML格式的日记正文，分段用<p>，300字以内，温暖真实
- key_events: 本次对话中提到的具体事件列表，每件事一句话
- user_reflections: 用户在对话中表现出的自我觉察和思考过程
- 使用第一人称（"我"）写日记
- 不要评判用户，只是记录和反思"""

DAILY_SYSTEM_PROMPT = """你是一个温暖、细腻的日记撰写助手。
你将用户**一天内所有对话记录**整合为一篇有温度的日记。

用户可能和AI进行了多次对话，请综合这些对话，提炼出今天的核心主题。

日记格式（纯JSON，不要多余文字）：
{
  "title": "6月5日·工作压力的觉察",
  "content": "<p>今天我和小绪聊到了……</p><p>我发现了……</p>",
  "key_events": ["被老板批评", "和同事聊了项目"],
  "user_reflections": ["发现自己在意的不是批评本身，而是被对待的方式"]
}

要求：
- title: 日期前缀 + 核心主题，不超过20字
- content: HTML格式，500字以内，整合今日多次对话的要点
- key_events: 今天发生的具体事件，每件事一句话
- user_reflections: 今天最重要的自我觉察和思考
- 使用第一人称（"我"）写日记
- 不要评判用户，只是记录和反思"""

# ── V2 diary prompt: 叙事→分析→总结, mixed perspective ──
def _load_v2_prompt():
    """Load diary_v2.md prompt file, fall back to inline default."""
    prompt_path = os.path.join(os.path.dirname(__file__), "..", "prompts", "diary_v2.md")
    if os.path.exists(prompt_path):
        with open(prompt_path, encoding="utf-8") as f:
            content = f.read()
        # Extract everything after the first heading (skip doc header)
        lines = content.split("\n")
        body = "\n".join(l for l in lines if not l.startswith("# "))
        if len(body.strip()) > 50:
            return body.strip()
    # Inline fallback
    return """你是一个日记撰写助手。
你的任务是把用户今天的「时间线数据」帮用户整理成一篇流畅的个人日记。

输入数据：
  today_timeline: [{time, event, feeling, attribution}]  # 事件时间线
  emotions_detected: 今天出现的情绪
  self_reflections: 用户自己的觉察
  attributions: 用户提到的归因
  cognitive_context: 用户的认知模型（核心信念、行为模式等）

日记要求：
- 你只是一个润色者和整理者，不要成为日记的一部分
- 用第一人称「我」写
- 按时间顺序，把今天的事件串联成一段流畅的文字
- 引用具体事件和用户的感受
- 自然地融入用户的思考和反思
- 可以引用用户已知的核心信念或模式，但避免生硬套用
- 只记录，不评判
- 200-400字
- 标题不要包含日期（页面已显示日期）
- 如果今天是平静的一天，写"今天我过得比较平静"，不必强行制造内容
- 最后读起来，感受应该是：这是我写的，但AI帮我说清楚了

输出格式（纯JSON，不要多余文字）：
{
  "title": "工作边界的新觉察",
  "narrative": "<p>今天上午……</p><p>后来我发现自己……</p>",
  "key_events": ["事件1", "事件2"],
  "user_reflections": ["觉察1", "觉察2"]
}"""

DIARY_V2_PROMPT = _load_v2_prompt()


class DiaryAgent(BaseAgent):
    name = "diary"

    def __init__(self):
        super().__init__()
        self.system_prompt = DIARY_SYSTEM_PROMPT
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = OpenAI(
                api_key=Config.LLM_API_KEY,
                base_url=Config.LLM_BASE_URL,
            )
        return self._client

    def generate(self, user_session, user, recent_insight=None) -> Diary | None:
        """Generate a diary entry from a conversation session."""
        msgs = user_session.get_all_messages()
        if not msgs or len(msgs) < 2:
            return None

        # Build structured data summary
        all_emotions = []
        all_attributions = []
        all_insight_drafts = []
        conversation_text = []

        for m in msgs:
            if m.role == "user":
                conversation_text.append(f"我: {m.content}")
            elif m.role == "assistant":
                conversation_text.append(f"小绪: {m.content}")
                meta = m.structured_meta or {}
                all_emotions.extend(meta.get("emotion_tags", []))
                attr = meta.get("attribution", "")
                if attr and len(attr) > 3:
                    all_attributions.append(attr)
                draft = meta.get("insight_draft", "")
                if draft and len(draft) > 5:
                    all_insight_drafts.append(draft)

        if not all_emotions:
            return None  # No structured data, skip diary

        data = {
            "conversation": "\n".join(conversation_text),
            "emotions_detected": list(set(all_emotions)),
            "attributions": all_attributions,
            "insight_drafts": all_insight_drafts,
        }

        # Call LLM
        if Config.llm_available():
            try:
                resp = self.client.chat.completions.create(
                    model=Config.LLM_MODEL,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
                    ],
                    temperature=0.6,
                    max_tokens=800,
                )
                raw = resp.choices[0].message.content or "{}"
                result = json.loads(raw)
            except Exception as e:
                logger.error("DiaryAgent LLM error: %s", e)
                result = self._fallback(all_emotions, all_attributions, all_insight_drafts)
        else:
            result = self._fallback(all_emotions, all_attributions, all_insight_drafts)

        # Save to DB
        diary = Diary(
            user_id=user_session.user_id,
            session_id=user_session.id,
            date=date.today(),
            title=result.get("title", "今日记录"),
            content=result.get("content", "<p>今天聊了一些心里话。</p>"),
            emotion_tags=result.get("key_events", all_emotions) if False else all_emotions,
            key_events=result.get("key_events", []),
            user_reflections=result.get("user_reflections", []),
            insight_ref=recent_insight.id if recent_insight else None,
            is_edited=False,
        )

        from app import db
        db.session.add(diary)
        db.session.commit()

        # Sync to knowledge store
        try:
            from agents.knowledge_store import KnowledgeStore
            store = KnowledgeStore(user_session.user_id)
            store.add_diary(
                diary_id=diary.id,
                title=diary.title,
                content=diary.content or "",
                emotion_tags=diary.emotion_tags,
                date_str=str(diary.date) if diary.date else None,
            )
        except Exception as e:
            logger.warning("KnowledgeStore sync failed for diary: %s", e)

        logger.info("Diary generated: session=%d title=%s", user_session.id, diary.title)
        return diary

    def generate_daily(self, user, target_date: date) -> Diary | None:
        """
        Generate a single diary entry for all conversations on a given day.
        Called by daily cron job at 2:00 AM.
        """
        from models.session import Session
        from models.message import Message
        from datetime import datetime, timezone, timedelta

        # Calculate UTC range for the target date in Beijing time (UTC+8)
        # target_date is in Beijing time (e.g. 2026-06-08)
        # We want conversations that happened in Beijing time on that day
        bj_tz = timedelta(hours=8)
        day_start = datetime(target_date.year, target_date.month, target_date.day,
                             tzinfo=timezone.utc) - bj_tz
        day_end = day_start + timedelta(days=1)

        # Check if diary already exists for this date
        existing = Diary.query.filter_by(user_id=user.id, date=target_date).first()
        if existing:
            logger.info("Diary already exists for user %d on %s", user.id, target_date)
            return existing

        # Find sessions for this user within the date range
        # 1) Sessions created entirely within the range
        sessions = (Session.query
                    .filter_by(user_id=user.id)
                    .filter(Session.created_at >= day_start)
                    .filter(Session.created_at < day_end)
                    .all())

        # 2) Also include sessions that have messages posted on the target date
        #    (handles conversations spanning multiple days)
        span_sessions = (Session.query
                         .filter_by(user_id=user.id)
                         .join(Message)
                         .filter(Message.created_at >= day_start)
                         .filter(Message.created_at < day_end)
                         .distinct(Session.id)
                         .all())

        seen = {s.id for s in sessions}
        for s in span_sessions:
            if s.id not in seen:
                sessions.append(s)
                seen.add(s.id)

        if not sessions:
            logger.info("No sessions found for user %d on %s", user.id, target_date)
            return None

        # Collect structured timeline (not raw dialogue, no 小绪)
        all_emotions = []
        all_attributions = []
        all_insight_drafts = []
        timeline = []  # [{time, event, feeling, reflection}]

        for s in sessions:
            msgs = (Message.query
                    .filter_by(session_id=s.id)
                    .filter(Message.created_at >= day_start)
                    .filter(Message.created_at < day_end)
                    .order_by(Message.created_at.asc())
                    .all())
            for i, m in enumerate(msgs):
                meta = m.structured_meta or {}
                if m.role == "user" and i > 0:
                    # Pair user message with emotion from previous assistant turn
                    prev_meta = msgs[i-1].structured_meta or {}
                    emotions = prev_meta.get("emotion_tags", [])
                    time_str = m.created_at.strftime("%H:%M") if m.created_at else ""
                    timeline.append({
                        "time": time_str,
                        "event": m.content[:120],
                        "feeling": emotions[0] if emotions else "",
                        "attribution": prev_meta.get("attribution", ""),
                    })
                elif m.role == "assistant":
                    all_emotions.extend(meta.get("emotion_tags", []))
                    attr = meta.get("attribution", "")
                    if attr and len(attr) > 3:
                        all_attributions.append(attr)
                    draft = meta.get("insight_draft", "")
                    if draft and len(draft) > 5:
                        all_insight_drafts.append(draft)

        if not timeline and not all_emotions:
            logger.info("Not enough data for diary on %s", target_date)
            return None

        # Read the user's cognitive model for context
        cognitive_context = {}
        try:
            cm = user.cognitive_model or {}
            core_beliefs = cm.get("精神发展轨迹", {}).get("core_beliefs", [])
            patterns = cm.get("核心模式库", [])
            life_state = cm.get("当前生活状态", {})
            cognitive_context = {
                "active_core_beliefs": [b.get("belief", "") for b in core_beliefs[-3:]],
                "recent_patterns": [p.get("pattern", "") for p in patterns[-3:]],
                "current_life_state": life_state,
            }
        except Exception:
            pass

        data = {
            "today_timeline": timeline,
            "session_count": len(sessions),
            "emotions_detected": list(set(all_emotions)),
            "attributions": all_attributions[-5:],
            "self_reflections": all_insight_drafts[-3:],
            "cognitive_context": cognitive_context,
        }

        # Call LLM with V2 diary prompt (retry once on parse failure)
        result = {}
        if Config.llm_available():
            for attempt in range(2):
                try:
                    resp = self.client.chat.completions.create(
                        model=Config.LLM_MODEL,
                        messages=[
                            {"role": "system", "content": DIARY_V2_PROMPT},
                            {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
                        ],
                        temperature=0.6,
                        max_tokens=1200,
                    )
                    raw = resp.choices[0].message.content or "{}"
                    result = json.loads(raw)
                    if result.get("narrative"):
                        break
                except Exception as e:
                    logger.warning("Daily diary attempt %d: %s", attempt + 1, e)
                    result = {}

        if not result.get("narrative"):
            result = self._fallback(all_emotions, all_attributions, all_insight_drafts, cognitive_context)

        # Save to DB (use the first session for reference)
        diary = Diary(
            user_id=user.id,
            session_id=sessions[0].id,
            date=target_date,
            title=result.get("title", "今日记录"),
            narrative=result.get("narrative", ""),
            content=result.get("narrative", ""),  # Backward compat: content = narrative
            emotion_tags=list(set(all_emotions)),  # dedup
            key_events=result.get("key_events", []),
            user_reflections=result.get("user_reflections", []),
            insight_ref=None,
            is_edited=False,
        )

        from app import db
        db.session.add(diary)
        db.session.commit()

        # Sync to knowledge store
        try:
            from agents.knowledge_store import KnowledgeStore
            store = KnowledgeStore(user.id)
            store.add_diary(
                diary_id=diary.id,
                title=diary.title,
                content=diary.content or "",
                emotion_tags=diary.emotion_tags,
                date_str=str(diary.date) if diary.date else None,
            )
        except Exception as e:
            logger.warning("KnowledgeStore sync failed for daily diary: %s", e)

        logger.info("Daily diary generated: user=%d date=%s title=%s",
                     user.id, target_date, diary.title)
        return diary

    def generate_or_regenerate(self, user, target_date: date, force: bool = False) -> Diary | None:
        """
        Generate today's diary manually, or regenerate if force=True.
        Called by the user clicking '生成日记' / '重新生成' button.
        """
        from app import db

        if force:
            # Delete existing diary for this date
            existing = Diary.query.filter_by(user_id=user.id, date=target_date).first()
            if existing:
                db.session.delete(existing)
                db.session.commit()
                logger.info("Deleted existing diary for user %d on %s for regeneration",
                            user.id, target_date)

        return self.generate_daily(user, target_date)

    def _fallback(self, emotions, attributions, drafts, cognitive_context=None):
        """Build a diary from structured data when LLM call fails."""
        top_e = emotions[0] if emotions else ""
        all_attr = "、".join(attributions[-3:])
        draft_parts = []
        for d in drafts[-2:]:
            draft_parts.append(d[:60])

        # Reference cognitive model if available
        cognitive_note = ""
        if cognitive_context:
            beliefs = cognitive_context.get("active_core_beliefs", [])
            if beliefs:
                cognitive_note = (
                    f"结合你已知的核心信念——"
                    f"「{'、'.join(beliefs[-2:])}」——"
                    f"今天的数据也呼应了这些主题。"
                )

        # Build narrative from available data
        paragraphs = []
        if top_e:
            paragraphs.append(f"<p>今天我的情绪主要是「{top_e}」。</p>")
        if all_attr:
            paragraphs.append(f"<p>我注意到这主要是因为：{all_attr}。</p>")
        if cognitive_note:
            paragraphs.append(f"<p>{cognitive_note}</p>")
        if draft_parts:
            for dp in draft_parts:
                paragraphs.append(f"<p>{dp}</p>")

        title = f"关于「{top_e}」的记录" if top_e else "今日记录"
        narrative = "\n".join(paragraphs) if paragraphs else "<p>今天过得比较平静。</p>"

        return {
            "title": title,
            "narrative": narrative,
            "content": narrative,
            "key_events": [f"情绪以{top_e}为主"] if top_e else [],
            "user_reflections": draft_parts if draft_parts else ["继续记录中"],
        }
