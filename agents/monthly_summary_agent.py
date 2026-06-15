"""MonthlySummaryAgent: generates 30-day period reports from first activity."""
import json
import logging
from datetime import date
from collections import Counter
from openai import OpenAI

from agent_framework.base import BaseAgent
from models.monthly_summary import MonthlySummary
from models.diary import Diary
from models.insight import Insight
from config import Config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个温暖、敏锐的成长分析师。
请基于用户一个30天周期的日记和洞察数据，生成一份成长总结报告。

输入包含 cognitive_evolution 数据，展示用户认知模型在这个周期内的变化：
- new_core_beliefs: 新增的核心信念
- pattern_evolution: 模式库的演变
- life_state_changes: 当前生活状态的变化
- overall_growth: 整体认知成长

在报告中，请将这些认知演变自然地融入叙述中——
比如「这个周期你形成了一个新的信念…」「你的核心模式从…演变为…」。

输出格式（纯JSON，不要多余文字）：
{
  "title": "第1期：从焦虑到觉察的旅程",
  "summary_text": "<p>这个周期对你来说是一个……</p><p>你从……</p>",
  "key_discoveries": ["你发现自己害怕的是被否定的方式", "你的焦虑主要来自比较"],
  "growth_timeline": [
    {"week": 1, "insight": "刚开始时……"},
    {"week": 2, "insight": "你开始注意到……"},
    {"week": 4, "insight": "到周期末你发现……"}
  ]
}

要求：
- summary_text: HTML格式，600字以内，分段用<p>
- key_discoveries: 3-5条关键发现
- growth_timeline: 按周总结，每周一条核心变化
- 引用 cognitive_evolution 数据，说明用户认知模型的具体演进"""


class MonthlySummaryAgent(BaseAgent):
    name = "monthly_summary"

    def __init__(self):
        super().__init__()
        self.system_prompt = SYSTEM_PROMPT
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = OpenAI(
                api_key=Config.LLM_API_KEY,
                base_url=Config.LLM_BASE_URL,
            )
        return self._client

    def generate(self, user, period: int) -> MonthlySummary:
        """Generate or return existing summary for a given 30-day period."""
        existing = MonthlySummary.query.filter_by(
            user_id=user.id, period=period
        ).first()
        if existing:
            return existing

        first_date = MonthlySummary.get_first_activity_date(user.id)
        period_start, period_end = MonthlySummary.get_period_range(first_date, period)

        # Gather data within this period
        diaries = (Diary.query
                   .filter_by(user_id=user.id)
                   .filter(Diary.date >= period_start)
                   .filter(Diary.date < period_end)
                   .all())

        insights = (Insight.query
                    .filter_by(user_id=user.id)
                    .filter(Insight.created_at >= period_start)
                    .filter(Insight.created_at < period_end)
                    .all())

        # Aggregate emotions
        all_emotions = []
        for d in diaries:
            all_emotions.extend(d.emotion_tags or [])
        for i in insights:
            all_emotions.extend(i.emotion_tags or [])
        emotion_freq = dict(Counter(all_emotions))

        # Aggregate attributions
        all_attributions = []
        for d in diaries:
            all_attributions.extend(d.user_reflections or [])
        for i in insights:
            all_attributions.extend(i.attribution_chain or [])
        attr_freq = dict(Counter(all_attributions))
        attr_freq = dict(sorted(attr_freq.items(), key=lambda x: -x[1])[:8])

        if not diaries and not insights:
            summary = MonthlySummary(
                user_id=user.id, period=period, period_start=period_start,
                title=f"第{period}期",
                summary_text="<p>这一期还没有足够的记录来生成总结。</p>",
                key_discoveries=[],
                growth_timeline=[],
                emotion_frequencies=emotion_freq,
                attribution_distribution=attr_freq,
                diary_count=0,
                insight_count=0,
            )
            from app import db
            db.session.add(summary)
            db.session.commit()
            return summary

        # Compute cognitive model evolution during this period
        cognitive_evolution = self._compute_cognitive_evolution(user, period_start, period_end)

        data = {
            "period": period,
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "diary_count": len(diaries),
            "insight_count": len(insights),
            "emotion_frequencies": emotion_freq,
            "attribution_frequencies": attr_freq,
            "diary_contents": [d.content[:200] for d in diaries[:5]],
            "insight_texts": [i.insight_text[:200] for i in insights[:5]],
            "growth_timeline_raw": [
                f"第{(d.date - period_start).days // 7 + 1}周: {d.title}" for d in diaries
            ],
            "cognitive_evolution": cognitive_evolution,
        }

        if Config.llm_available():
            try:
                resp = self.client.chat.completions.create(
                    model=Config.LLM_MODEL,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
                    ],
                    temperature=0.5,
                    max_tokens=1024,
                )
                raw = resp.choices[0].message.content or "{}"
                result = json.loads(raw)
            except Exception as e:
                logger.error("MonthlySummaryAgent error: %s", e)
                result = self._fallback(data)
        else:
            result = self._fallback(data)

        summary = MonthlySummary(
            user_id=user.id, period=period, period_start=period_start,
            title=result.get("title", f"第{period}期"),
            summary_text=result.get("summary_text", "<p>继续记录，会有更多发现。</p>"),
            key_discoveries=result.get("key_discoveries", []),
            growth_timeline=result.get("growth_timeline", []),
            emotion_frequencies=emotion_freq,
            attribution_distribution=attr_freq,
            diary_count=len(diaries),
            insight_count=len(insights),
        )

        from app import db
        db.session.add(summary)
        db.session.commit()

        logger.info("MonthlySummary generated: period %d", period)
        return summary

    def _compute_cognitive_evolution(self, user, period_start, period_end):
        """
        Compute what changed in the cognitive model during this period.
        Returns a dict describing new core beliefs, pattern evolution, etc.
        """
        cm = user.cognitive_model or {}

        # Core beliefs evolution
        core_beliefs = cm.get("精神发展轨迹", {}).get("core_beliefs", [])
        new_beliefs = [b for b in core_beliefs
                       if b.get("formed_at") and period_start <= self._parse_date(b["formed_at"]) < period_end]

        # Pattern library changes
        patterns = cm.get("核心模式库", [])
        new_patterns = [p for p in patterns
                        if p.get("first_seen") and period_start <= self._parse_date(p["first_seen"]) < period_end]
        evolved_patterns = [p for p in patterns
                           if p.get("last_seen") and period_start <= self._parse_date(p["last_seen"]) < period_end
                           and (not p.get("first_seen") or self._parse_date(p.get("first_seen", "")) < period_start)]

        # Life state changes
        life_state = cm.get("当前生活状态", {})

        return {
            "new_core_beliefs": [b.get("belief", "") for b in new_beliefs],
            "active_core_beliefs": [b.get("belief", "") for b in core_beliefs],
            "new_patterns": [p.get("pattern", "") for p in new_patterns],
            "evolved_patterns": [p.get("pattern", "") for p in evolved_patterns],
            "life_state_changes": life_state,
            "overall_growth": (
                f"新增了{len(new_beliefs)}个核心信念，"
                f"形成了{len(new_patterns)}个新模式，"
                f"{len(evolved_patterns)}个已有模式持续演进"
            ),
        }

    @staticmethod
    def _parse_date(date_str: str):
        """Safely parse date string, returns a sentinel min date on failure."""
        from datetime import date as dt_date
        try:
            return dt_date.fromisoformat(date_str)
        except (ValueError, TypeError):
            return dt_date.min

    def _fallback(self, data: dict) -> dict:
        top_emotions = sorted(data.get("emotion_frequencies", {}).items(),
                              key=lambda x: -x[1])[:3]
        emotions_text = "、".join(f"{k}({v}次)" for k, v in top_emotions)

        cognitive_evolution = data.get("cognitive_evolution", {})
        growth_note = ""
        if cognitive_evolution:
            new_beliefs = cognitive_evolution.get("new_core_beliefs", [])
            if new_beliefs:
                growth_note = f"<p>认知成长：形成了新的核心信念——「{'、'.join(new_beliefs)}」</p>"

        return {
            "title": f"第{data.get('period', '?')}期记录",
            "summary_text": f"<p>这个周期你记录了{data['diary_count']}次对话。</p>"
                           f"<p>主要情绪：{emotions_text}</p>"
                           + growth_note,
            "key_discoveries": ["继续记录，更多洞察会浮现"],
            "growth_timeline": [{"week": 1, "insight": "开始记录"}],
        }
