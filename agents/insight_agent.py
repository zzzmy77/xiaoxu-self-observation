"""InsightAgent: generates cross-session insights from structured data."""
import json
import logging
from datetime import datetime, timezone
from openai import OpenAI

from agent_framework.base import BaseAgent
from models.insight import Insight
from config import Config

logger = logging.getLogger(__name__)

INSIGHT_SYSTEM_PROMPT = """你是一个自我观察洞察分析师。用户的情感数据和归因信息是由对话中提取的。
请基于以下数据，生成一段温暖、有洞察力的自我观察总结。

输出格式（纯JSON，不要多余文字）：
{
  "emotion_tags": ["焦虑", "压力"],
  "insight_text": "你最近的焦虑主要集中在工作场景……",
  "attribution_summary": "比较和完美主义"
}"""


class InsightAgent(BaseAgent):
    name = "insight"

    def __init__(self):
        super().__init__()
        self.system_prompt = INSIGHT_SYSTEM_PROMPT
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = OpenAI(
                api_key=Config.LLM_API_KEY,
                base_url=Config.LLM_BASE_URL,
            )
        return self._client

    def run(self, context: dict) -> Insight | None:
        session = context.get("session")
        user = context.get("user")
        if not session or not user:
            return None

        # Gather recent session data for this user
        from models.session import Session
        from models.message import Message

        recent_sessions = (Session.query
                           .filter_by(user_id=user.id)
                           .order_by(Session.created_at.desc())
                           .limit(5)
                           .all())

        all_emotions = []
        all_attributions = []
        all_insights = []
        session_ids = [s.id for s in recent_sessions]

        msgs = (Message.query
                .filter(Message.session_id.in_(session_ids))
                .filter(Message.role == "assistant")
                .order_by(Message.created_at.asc())
                .all())

        for msg in msgs:
            meta = msg.structured_meta or {}
            all_emotions.extend(meta.get("emotion_tags", []))
            attr = meta.get("attribution", "")
            if attr and len(attr) > 3:
                all_attributions.append(attr)
            draft = meta.get("insight_draft", "")
            if draft and len(draft) > 10:
                all_insights.append(draft)

        if not all_emotions and not all_attributions:
            # Not enough data for an insight
            return None

        # Use LLM to generate insight summary
        data_summary = {
            "emotion_frequencies": {e: all_emotions.count(e) for e in set(all_emotions)},
            "attributions": all_attributions[-10:],
            "recent_insight_drafts": all_insights[-5:],
            "session_count": len(recent_sessions),
        }

        if not Config.llm_available():
            result = self._fallback_insight(all_emotions)
        else:
            try:
                resp = self.client.chat.completions.create(
                    model=Config.LLM_MODEL,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": json.dumps(data_summary, ensure_ascii=False)},
                    ],
                    temperature=0.5,
                    max_tokens=512,
                )
                raw = resp.choices[0].message.content or "{}"
                result = json.loads(raw)
            except Exception as e:
                logger.error("InsightAgent LLM error: %s", e)
                result = self._fallback_insight(all_emotions)

        insight = Insight(
            user_id=user.id,
            session_id=session.id,
            emotion_tags=result.get("emotion_tags", list(set(all_emotions))),
            attribution_chain=all_attributions[-5:],
            insight_text=result.get("insight_text", ""),
            pattern_ref={
                "session_count": len(recent_sessions),
                "emotion_frequencies": data_summary["emotion_frequencies"],
            },
        )

        from app import db
        db.session.add(insight)
        db.session.commit()

        # Sync to knowledge store
        try:
            from agents.knowledge_store import KnowledgeStore
            store = KnowledgeStore(user.id)
            store.add_insight(
                insight_id=insight.id,
                insight_text=insight.insight_text or "",
                emotion_tags=insight.emotion_tags,
                date_str=str(insight.created_at.date()) if insight.created_at else None,
            )
        except Exception as e:
            logger.warning("KnowledgeStore sync failed for insight: %s", e)

        return insight

    def _fallback_insight(self, all_emotions: list) -> dict:
        top_emotion = all_emotions[0] if all_emotions else "未识别"
        return {
            "emotion_tags": list(set(all_emotions)),
            "insight_text": f"你最近的情绪以「{top_emotion}」为主。继续记录，你会发现更多关于自己的模式。",
            "attribution_summary": "数据不足，正在积累中",
        }
