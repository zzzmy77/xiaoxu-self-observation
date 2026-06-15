"""
RecognitionAgent: 对话分析，不生成回复文本。

职责：
1. 分析本次对话的情绪变化轨迹并输出一句总结
2. 检测当前归因与历史洞察的模式关联
3. 生成一句可行动的提示

触发逻辑：
- L1（前端）：每轮对话后用规则比对更新情绪曲线，零成本
- L2（后端条件触发）：满3轮或 stage=closure 时调用本 Agent
- L3（异步）：对话结束后10秒调用跨会话模式匹配
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from openai import OpenAI

from agent_framework.base import BaseAgent
from config import Config

logger = logging.getLogger(__name__)

ANALYSIS_SYSTEM_PROMPT = """你是一个对话分析助手。
你的工作不是回复用户，而是分析对话数据，提供三个输出。

输入：
- 本次对话的所有轮次数据（按时间排列，每轮含 emotion_tags / intensity / attribution / stage）
- 用户最近的历史洞察文本列表（如有关联，否则为空列表）

输出 1 — 情绪变化总结：
将用户的情绪变化归纳为一句话。
示例："你从焦虑(强度4)开始，经过归因发现根源是比较，最后放松到了觉察(强度1)"

输出 2 — 跨会话模式连接（可选）：
如果本次对话的归因和用户历史洞察有关联，输出一句通俗的关联提示。
没有关联则输出空字符串。
示例："这和你上周聊到的害怕被否定是同一个模式"
示例："你今天提到了'总是觉得不够好'，之前你也多次提到自我怀疑"

输出 3 — 一句可行动建议：
用第二人称"你"，20字以内，具体可执行。
示例："下次恐慌时，先问自己：有没有例外？"
示例："试着把'我做不到'换成'我还没做到'"

输出格式（纯JSON，不要多余文字）：
{
  "emotion_summary": "你从焦虑(4)开始，经过归因发现根源是比较，最后降到觉察(1)",
  "pattern_match": "这和你上周聊到的害怕被否定是同一个模式",
  "actionable_tip": "下次恐慌时，先问自己有没有例外"
}
"""


class RecognitionAgent(BaseAgent):
    """分析型 Agent，不生成回复文本，只分析对话数据。"""
    name = "recognition"

    def __init__(self):
        super().__init__()
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = OpenAI(
                api_key=Config.LLM_API_KEY,
                base_url=Config.LLM_BASE_URL,
            )
        return self._client

    def analyze(self, session, user) -> dict:
        """
        分析对话，返回识别结果。
        L2 条件触发时调用。
        """
        from models.message import Message

        # 读取本次 session 全部消息
        msgs = (Message.query
                .filter_by(session_id=session.id)
                .order_by(Message.created_at.asc())
                .all())

        if not msgs or len(msgs) < 2:
            return self._empty_result()

        # 提取结构化数据轮次
        turns = []
        for m in msgs:
            meta = m.structured_meta or {}
            if m.role == "assistant" and meta.get("emotion_tags"):
                turns.append({
                    "role": "assistant",
                    "emotion": meta.get("emotion_tags", [None])[0],
                    "intensity": meta.get("emotion_intensity", 0),
                    "attribution": meta.get("attribution", ""),
                    "stage": meta.get("stage", "empathy"),
                })
            elif m.role == "user":
                turns.append({
                    "role": "user",
                    "text": m.content[:80],
                })

        if not any(t.get("emotion") for t in turns if t["role"] == "assistant"):
            return self._empty_result()

        # 读取历史洞察
        history_insights = []
        try:
            from models.insight import Insight
            recent = (Insight.query
                      .filter_by(user_id=user.id)
                      .order_by(Insight.created_at.desc())
                      .limit(5)
                      .all())
            history_insights = [{"text": i.insight_text, "tags": i.emotion_tags} for i in recent if i.insight_text]
        except Exception:
            pass

        # 调用 LLM
        data = {
            "turns": turns,
            "history_insights": history_insights,
        }

        result = self._call_llm(data)
        if result.get("pattern_match"):
            self._save_pattern_match(session, user, result["pattern_match"])
        return result

    def match_pattern(self, user) -> dict:
        """
        跨会话模式匹配。
        L3 异步调用：读取最近对话的归因 + 历史洞察，检测模式。
        """
        from models.session import Session
        from models.message import Message
        from models.insight import Insight

        # 最近一次 conversation session
        recent_sessions = (Session.query
                           .filter_by(user_id=user.id)
                           .order_by(Session.created_at.desc())
                           .limit(3)
                           .all())

        if not recent_sessions:
            return {"pattern_match": ""}

        # 收集最近的结构化数据
        recent_turns = []
        for s in recent_sessions:
            msgs = (Message.query
                    .filter_by(session_id=s.id)
                    .order_by(Message.created_at.desc())
                    .limit(10)
                    .all())
            for m in msgs:
                meta = m.structured_meta or {}
                if m.role == "assistant" and meta.get("emotion_tags"):
                    recent_turns.append({
                        "emotion": meta.get("emotion_tags", [None])[0],
                        "attribution": meta.get("attribution", ""),
                        "stage": meta.get("stage", ""),
                    })

        history_insights = []
        recent_ins = (Insight.query
                      .filter_by(user_id=user.id)
                      .order_by(Insight.created_at.desc())
                      .limit(10)
                      .all())
        history_insights = [{"text": i.insight_text, "tags": i.emotion_tags} for i in recent_ins if i.insight_text]

        if not history_insights or not recent_turns:
            return {"pattern_match": ""}

        data = {
            "recent_turns": recent_turns,
            "history_insights": history_insights,
            "mode": "pattern_only",
        }

        return self._call_llm(data)

    def _call_llm(self, data: dict) -> dict:
        """调用 LLM 进行分析。"""
        if not Config.llm_available():
            return self._empty_result()

        try:
            resp = self.client.chat.completions.create(
                model=Config.LLM_MODEL,
                messages=[
                    {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
                ],
                temperature=0.4,
                max_tokens=400,
            )
            raw = resp.choices[0].message.content or "{}"
            result = json.loads(raw)
            return {
                "emotion_summary": result.get("emotion_summary", ""),
                "pattern_match": result.get("pattern_match", ""),
                "actionable_tip": result.get("actionable_tip", ""),
            }
        except Exception as e:
            logger.error("RecognitionAgent LLM error: %s", e)
            return self._empty_result()

    def _save_pattern_match(self, session, user, pattern_text: str):
        """将模式匹配结果写入最新洞察的 pattern_ref。"""
        try:
            from models.insight import Insight
            latest = (Insight.query
                      .filter_by(user_id=user.id, session_id=session.id)
                      .order_by(Insight.created_at.desc())
                      .first())
            if latest:
                ref = latest.pattern_ref or {}
                ref["recognition_match"] = pattern_text
                latest.pattern_ref = ref
                from app import db
                db.session.commit()
        except Exception as e:
            logger.warning("Failed to save pattern match: %s", e)

    def _empty_result(self) -> dict:
        return {
            "emotion_summary": "",
            "pattern_match": "",
            "actionable_tip": "",
        }
