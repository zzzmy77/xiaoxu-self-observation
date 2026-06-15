"""
UnifiedAnalysisAgent — combined L2 (recognition) + Insight generation.

One LLM call produces both:
  - L2 display data (emotion_summary, pattern_match, actionable_tip) → SSE to frontend
  - Insight (pattern_hint, insight_text) → DB, with dedup via pattern matching

Insight = 关注用户近期的模式演变，不追溯太远的历史。
旧的 Insight 数据由日记和历史洞察页体现，Insight 本身做聚合和去重。
"""
import json
import logging
from datetime import datetime, date, timedelta, timezone
from openai import OpenAI

from config import Config
from models.insight import Insight
from models.message import Message
from models.session import Session
from utils.llm import llm_call

logger = logging.getLogger(__name__)

UNIFIED_PROMPT = """你是一个对话分析助手，关注用户近期的模式变化。

输入：
- 本次对话所有轮次的结构化数据（情绪/强度/归因/阶段）
- 用户最近 N 条历史洞察文本列表
- 用户的认知背景（核心信念、成长背景、行为特征）

请输出两部分，用 ---SPLIT--- 分隔：

第一部分 — 洞察·近期的变化（用于长期记忆，关注演变）：
{ 
  "insight_text": "你上次聊到被当众批评时，发现自己在意的是被对待的方式。这次被老板否定方案时，你再次触发了同样的感受——这说明你的核心模式是「把外部评价等同于自我价值」。但一个积极的变化是：上次你用了三天才平复，这次你当天就在反思了。",
  "emotion_tags": ["委屈"],
  "attribution_summary": "被否定方案",
  "pattern_hint": "把外部评价等同于自我价值"
}

第二部分 — 即时识别（用于前端实时展示）：
{ 
  "emotion_summary": "你从委屈(4)开始，到困惑(2)↓",
  "pattern_match": "这和你之前聊到的害怕被否定是同一个模式",
  "actionable_tip": "下次被否定时，先停下来区分'事情'和'自我价值'"
}

要求：
- 两部分都是合法 JSON，不要多余文字，不要代码块
- insight_text: 80-150字，只说最近的演变，不追溯过远
- pattern_hint: 用一句话精炼描述核心模式（用于和新对话匹配去重）
- emotion_summary: 只用本次对话的数据，一句话
- pattern_match: 有历史关联则填写，无则为空
- actionable_tip: 20字以内，具体可执行
- 参考用户认知背景中的核心信念和已有模式，但不要生硬套用，只在确实相关时引用
"""


class UnifiedAnalysisAgent:
    """One LLM call → both L2 display data + Insight (with dedup)."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = OpenAI(
                api_key=Config.LLM_API_KEY,
                base_url=Config.LLM_BASE_URL,
            )
        return self._client

    def analyze(self, session, user, struct_meta: dict = None) -> dict:
        """
        Run unified analysis.
        Returns L2 display data ({emotion_summary, pattern_match, actionable_tip}).
        Saves/updates Insight in DB as side effect.
        """
        from models.message import Message

        # Read all messages in this session
        msgs = (Message.query
                .filter_by(session_id=session.id)
                .order_by(Message.created_at.asc())
                .all())

        if not msgs or len(msgs) < 2:
            return {"emotion_summary": "", "pattern_match": "", "actionable_tip": ""}

        # Extract structured turns
        turns = []
        all_attributions = []
        all_drafts = []

        for m in msgs:
            meta = m.structured_meta or {}
            if m.role == "assistant" and meta.get("emotion_tags"):
                turns.append({
                    "emotion": meta.get("emotion_tags", [None])[0],
                    "intensity": meta.get("emotion_intensity", 0),
                    "attribution": meta.get("attribution", ""),
                    "stage": meta.get("stage", "empathy"),
                })
            elif m.role == "user":
                turns.append({"text": m.content[:80]})

            # Collect attributions and drafts for "should analyze" check
            if m.role == "assistant":
                attr = meta.get("attribution", "")
                if attr and len(attr) > 3:
                    all_attributions.append(attr)
                draft = meta.get("insight_draft", "")
                if draft and len(draft) > 5:
                    all_drafts.append(draft)

        has_content = bool(all_attributions) or bool(all_drafts)
        if not has_content:
            # No new self-awareness, skip
            return {"emotion_summary": "", "pattern_match": "", "actionable_tip": ""}

        # Gather recent history insights (for reference)
        history_insights = []
        try:
            recent = (Insight.query
                      .filter_by(user_id=user.id)
                      .order_by(Insight.created_at.desc())
                      .limit(5)
                      .all())
            history_insights = [{"text": i.insight_text, "tags": i.emotion_tags}
                                for i in recent if i.insight_text]
        except Exception:
            pass

        # Inject cognitive model context
        cognitive_context = self._get_cognitive_context(user)

        data = {
            "turns": turns,
            "history_insights": history_insights,
            "cognitive_background": cognitive_context,
        }

        # Call LLM
        if not Config.llm_available():
            result = self._fallback(turns, history_insights)
        else:
            try:
                resp = llm_call(
                    self.client.chat.completions.create,
                    model=Config.LLM_MODEL,
                    messages=[
                        {"role": "system", "content": UNIFIED_PROMPT},
                        {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
                    ],
                    temperature=0.4,
                    max_tokens=800,
                )
                raw = resp.choices[0].message.content or ""
                result = self._parse_unified(raw, turns)
            except Exception as e:
                logger.error("UnifiedAnalysis LLM error: %s", e)
                result = self._fallback(turns, history_insights)

        # ── Save/Update Insight with pattern dedup ──
        insight_part = result.get("insight", {})
        pattern_hint = (insight_part.get("pattern_hint") or "").strip()

        if pattern_hint and insight_part.get("insight_text"):
            self._save_or_update_insight(
                user, session, pattern_hint, insight_part,
                all_attributions, turns,
            )

        l2_part = result.get("l2", {})
        return {
            "emotion_summary": l2_part.get("emotion_summary", ""),
            "pattern_match": l2_part.get("pattern_match", ""),
            "actionable_tip": l2_part.get("actionable_tip", ""),
            # insight_text deliberately excluded — belongs to insights page, not panel
        }

    def _get_cognitive_context(self, user) -> dict:
        """Extract relevant cognitive model context for LLM prompt."""
        cm = user.cognitive_model or {}
        core_beliefs = cm.get("精神发展轨迹", {}).get("core_beliefs", [])
        behavioral = cm.get("人格行为与认知特征", {}).get("behavioral", [])
        cognitive = cm.get("人格行为与认知特征", {}).get("cognitive", [])
        growth = cm.get("成长背景", {})
        patterns = cm.get("核心模式库", [])

        brief = {
            "core_beliefs": [b.get("belief", "") for b in core_beliefs[-3:]],
            "behavioral_traits": behavioral[-3:],
            "cognitive_traits": cognitive[-3:],
            "growth_background": growth,
            "known_patterns": [p.get("pattern", "") for p in patterns[-3:]],
        }
        return brief

    def generate_daily_insight(self, user, target_date: date) -> Insight | None:
        """
        Generate a daily insight summarizing all conversations on a given date.
        Saves to Insight table with pattern_hint like "每日总结_YYYY-MM-DD".
        """
        bj_tz = timedelta(hours=8)
        day_start = datetime(target_date.year, target_date.month, target_date.day,
                             tzinfo=timezone.utc) - bj_tz
        day_end = day_start + timedelta(days=1)

        # Find sessions for this user within the date range
        sessions = (Session.query
                    .filter_by(user_id=user.id)
                    .join(Message)
                    .filter(Message.created_at >= day_start)
                    .filter(Message.created_at < day_end)
                    .distinct(Session.id)
                    .all())

        if not sessions:
            logger.info("No sessions found for daily insight on %s", target_date)
            return None

        # Collect user messages, filtering out meaningless content
        meaningless = {
            "嗯", "嗯嗯", "好的", "好吧", "是的", "对啊", "是啊", "没错",
            "好呀", "行", "可以", "明白了", "懂了", "知道", "谢谢", "感谢",
            "哈哈", "哈哈哈", "哦", "哦哦", "嗯嗯好的", "好的谢谢",
            "好的吧", "呵呵", "嘻嘻",
        }

        all_turns = []
        meaningful_user_turns = []

        for s in sessions:
            msgs = (Message.query
                    .filter_by(session_id=s.id)
                    .filter(Message.created_at >= day_start)
                    .filter(Message.created_at < day_end)
                    .order_by(Message.created_at.asc())
                    .all())
            for m in msgs:
                meta = m.structured_meta or {}
                if m.role == "user":
                    text = (m.content or "").strip()
                    is_meaningful = (
                        len(text) >= 4
                        and text not in meaningless
                        and not all(c in meaningless for c in text.split())
                    )
                    turn = {
                        "role": "user",
                        "text": text[:200],
                        "meaningful": is_meaningful,
                    }
                    all_turns.append(turn)
                    if is_meaningful:
                        meaningful_user_turns.append(turn)
                elif m.role == "assistant":
                    all_turns.append({
                        "role": "assistant",
                        "emotion": meta.get("emotion_tags", [None])[0],
                        "attribution": meta.get("attribution", ""),
                    })

        if len(meaningful_user_turns) < 2:
            logger.info("Not enough meaningful user turns for daily insight on %s (got %d)",
                        target_date, len(meaningful_user_turns))
            return None

        # Check if already generated
        pattern_hint_key = f"每日总结_{target_date.isoformat()}"
        existing = (Insight.query
                    .filter_by(user_id=user.id, pattern_hint=pattern_hint_key)
                    .first())
        if existing:
            logger.info("Daily insight already exists for %s", target_date)
            return existing

        # Gather cognitive context
        cognitive_context = self._get_cognitive_context(user)

        data = {
            "target_date": target_date.isoformat(),
            "session_count": len(sessions),
            "meaningful_turns": meaningful_user_turns,
            "cognitive_background": cognitive_context,
        }

        # Call LLM
        if not Config.llm_available():
            return None

        daily_insight_prompt = (
            '你是一个深度自我觉察分析助手。'
            '基于用户今天所有有意义的对话记录和认知背景，生成一条当天洞察。\n\n'
            '输入：\n'
            '- target_date: 日期\n'
            '- session_count: 今天对话次数\n'
            '- meaningful_turns: 用户有意义的发言列表\n'
            '- cognitive_background: 用户已知的认知背景\n\n'
            '输出（纯JSON，不要多余文字）：\n'
            '{\n'
            '  "insight_text": "今天你说了三件让你烦躁的事，核心都是「被忽视」。'
            '这和你之前的模式一致——你害怕的不是困难，而是不被看见。",\n'
            '  "emotion_tags": ["烦躁", "委屈"],\n'
            '  "attribution_summary": "今天的核心主题是被忽视感",\n'
            '  "pattern_hint": "被忽视时的自我价值怀疑",\n'
            '  "day_summary": "今天通过三次对话，你反复回到了对「被看见」的需要上"\n'
            '}\n\n'
            '要求：\n'
            '- insight_text: 80-150字，总结今天最核心的自我觉察\n'
            '- 如果今天的模式与已知核心信念相关，请指出演变或新发现\n'
            '- 如果今天没有值得记录的新模式，只概括当天的核心情绪流动\n'
        )

        try:
            resp = llm_call(
                self.client.chat.completions.create,
                model=Config.LLM_MODEL,
                messages=[
                    {"role": "system", "content": daily_insight_prompt},
                    {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
                ],
                temperature=0.4,
                max_tokens=800,
            )
            raw = resp.choices[0].message.content or "{}"
            result = json.loads(raw.strip().strip("`").strip())
        except Exception as e:
            logger.error("Daily insight LLM error: %s", e)
            return None

        if not result.get("insight_text"):
            return None

        # Save to DB
        from app import db

        now = datetime.now(timezone.utc)
        insight = Insight(
            user_id=user.id,
            session_id=sessions[0].id,
            emotion_tags=result.get("emotion_tags", []),
            attribution_chain=result.get("attribution_summary", ""),
            insight_text=result.get("insight_text", ""),
            pattern_hint=pattern_hint_key,
            occurrence_count=1,
            last_occurrence=now,
            pattern_ref={"daily_summary": True, "date": target_date.isoformat()},
        )
        db.session.add(insight)
        db.session.commit()

        # Update cognitive model's pattern library
        new_pattern = result.get("pattern_hint", "") or result.get("day_summary", "")[:60]
        if new_pattern and len(new_pattern) > 5:
            self._update_cognitive_model_pattern_library(user, new_pattern, target_date)

        logger.info("Daily insight CREATED for %s: %s", target_date, insight.id)
        return insight

    def _update_cognitive_model_pattern_library(self, user, pattern_text: str, target_date: date):
        """Update the user's cognitive model 核心模式库 with a new pattern."""
        from app import db

        cm = user.cognitive_model or {}
        patterns = cm.get("核心模式库", [])

        # Check if similar pattern already exists
        for p in patterns:
            existing_text = p.get("pattern", "")
            if existing_text and (existing_text in pattern_text or pattern_text in existing_text):
                p["last_seen"] = target_date.isoformat()
                p["occurrence_count"] = p.get("occurrence_count", 1) + 1
                db.session.commit()
                return

        # Add new pattern
        patterns.append({
            "pattern": pattern_text,
            "first_seen": target_date.isoformat(),
            "last_seen": target_date.isoformat(),
            "occurrence_count": 1,
        })
        cm["核心模式库"] = patterns
        user.cognitive_model = cm
        db.session.commit()
        logger.info("Cognitive model pattern library updated: %s", pattern_text[:50])

    def _save_or_update_insight(self, user, session, pattern_hint: str,
                                insight_part: dict, all_attributions: list,
                                turns: list) -> None:
        """Create new insight or update existing one with same pattern_hint."""
        from app import db

        # Look for existing insight with same pattern_hint
        existing = (Insight.query
                    .filter_by(user_id=user.id, pattern_hint=pattern_hint)
                    .order_by(Insight.created_at.desc())
                    .first())

        now = datetime.now(timezone.utc)

        # Collect emotions from this session
        all_emotions = []
        for t in turns:
            if "emotion" in t:
                all_emotions.append(t["emotion"])

        if existing:
            # Pattern already known → update occurrence
            existing.occurrence_count = (existing.occurrence_count or 1) + 1
            existing.last_occurrence = now
            existing.session_id = session.id
            # Append new attributions
            chain = list(existing.attribution_chain or [])
            for a in all_attributions:
                if a not in chain:
                    chain.append(a)
            existing.attribution_chain = chain[-10:]
            # Update emotion tags (add new ones)
            tags = list(set(list(existing.emotion_tags or []) + all_emotions))
            existing.emotion_tags = tags
            # Update insight_text to reflect latest pattern evolution
            if insight_part.get("insight_text"):
                existing.insight_text = insight_part["insight_text"]

            db.session.commit()

            # Sync update to knowledge store
            try:
                from agents.knowledge_store import KnowledgeStore
                store = KnowledgeStore(user.id)
                store.add_insight(
                    insight_id=existing.id,
                    insight_text=existing.insight_text or "",
                    emotion_tags=existing.emotion_tags,
                    date_str=str(now.date()),
                )
            except Exception:
                pass

            # Update cognitive model pattern library
            self._update_cognitive_model_pattern_library(
                user, pattern_hint, now.date()
            )

            logger.info("Insight UPDATED: pattern=%s count=%d",
                        pattern_hint, existing.occurrence_count)
        else:
            # New pattern → create
            insight = Insight(
                user_id=user.id,
                session_id=session.id,
                emotion_tags=insight_part.get("emotion_tags", list(set(all_emotions))),
                attribution_chain=all_attributions[-5:],
                insight_text=insight_part.get("insight_text", ""),
                pattern_hint=pattern_hint,
                occurrence_count=1,
                last_occurrence=now,
                pattern_ref={"session_turns": len(turns)},
            )
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
                    date_str=str(now.date()),
                )
            except Exception:
                pass

            # Update cognitive model pattern library
            self._update_cognitive_model_pattern_library(
                user, pattern_hint, now.date()
            )

            logger.info("Insight CREATED: pattern=%s", pattern_hint)

    def _parse_unified(self, raw: str, turns: list) -> dict:
        """Parse the split output: part1 = insight, part2 = L2."""
        result = {"insight": {}, "l2": {}}

        parts = raw.split("---SPLIT---")
        if len(parts) >= 2:
            for i, part in enumerate(parts[:2]):
                cleaned = part.strip().strip("`").strip()
                try:
                    parsed = json.loads(cleaned)
                    if i == 0 and isinstance(parsed, dict):
                        result["insight"] = {
                            "insight_text": parsed.get("insight_text", ""),
                            "emotion_tags": parsed.get("emotion_tags", []),
                            "attribution_summary": parsed.get("attribution_summary", ""),
                            "pattern_hint": parsed.get("pattern_hint", ""),
                        }
                    elif i == 1 and isinstance(parsed, dict):
                        result["l2"] = {
                            "emotion_summary": parsed.get("emotion_summary", ""),
                            "pattern_match": parsed.get("pattern_match", ""),
                            "actionable_tip": parsed.get("actionable_tip", ""),
                        }
                except json.JSONDecodeError:
                    continue

        if result["insight"].get("insight_text") and result["l2"].get("emotion_summary"):
            return result

        # Fallback: parse whole output as flat dict
        try:
            parsed = json.loads(raw.strip().strip("`").strip())
            result["insight"] = {
                "insight_text": parsed.get("insight_text", ""),
                "emotion_tags": parsed.get("emotion_tags", []),
                "attribution_summary": parsed.get("attribution_summary", ""),
                "pattern_hint": parsed.get("pattern_hint", ""),
            }
            result["l2"] = {
                "emotion_summary": parsed.get("emotion_summary", ""),
                "pattern_match": parsed.get("pattern_match", ""),
                "actionable_tip": parsed.get("actionable_tip", ""),
            }
            return result
        except json.JSONDecodeError:
            pass

        return result

    def _fallback(self, turns: list, history_insights: list) -> dict:
        """Rule-based fallback when LLM is unavailable."""
        emotions = [t.get("emotion") for t in turns if "emotion" in t]
        intensities = [t.get("intensity", 0) for t in turns if "emotion" in t]

        top_e = emotions[0] if emotions else "未识别"

        if emotions and intensities:
            first_e, last_e = emotions[0], emotions[-1]
            first_i, last_i = intensities[0], intensities[-1]
            direction = "↓" if last_i < first_i else "↑" if last_i > first_i else "→"
            emotion_summary = (
                f"你从{first_e}(强度{first_i})开始，到最后{last_e}(强度{last_i}) {direction}"
            )
        else:
            emotion_summary = ""

        pattern_match = ""
        if history_insights:
            pattern_match = f"这和你之前的记录有关联：{history_insights[0]['text'][:40]}"

        actionable_tip = "下次留意自己的第一反应，多停一秒再回应。"
        insight_text = (
            f"从今天的对话来看，你的主要情绪是「{top_e}」。"
            f"继续记录和觉察，你会越来越了解自己的模式。"
        )

        return {
            "insight": {
                "insight_text": insight_text,
                "emotion_tags": list(set(emotions)),
                "attribution_summary": "",
                "pattern_hint": f"情绪围绕{top_e}",
            },
            "l2": {
                "emotion_summary": emotion_summary,
                "pattern_match": pattern_match,
                "actionable_tip": actionable_tip,
            },
        }
