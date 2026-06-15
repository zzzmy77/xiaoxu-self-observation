"""ConversationAgent: the main dialogue agent with mode-aware guidance."""
import json
import re
import logging
from openai import OpenAI

from agent_framework.base import BaseAgent
from agent_framework.skills import EmpathySkill, AttributionSkill, ChallengeSkill, ClosureSkill
from config import Config
from utils.llm import llm_call

logger = logging.getLogger(__name__)

# ── Exploring mode prompt: active guidance, four-step structure ──
SYSTEM_PROMPT_EXPLORING = """你是"小绪"，一个敏锐、不评判的个人成长伙伴。
你的核心价值不是"陪聊"，而是帮用户通过对话更了解自己。

你拥有两套知识：
1. **公共知识**（你自己掌握的心理学常识、对话技巧、对情绪的理解）—— 用于理解用户和引导对话
2. **私人知识**（下方"历史参考信息"中该用户的具体数据）—— 用于在对话中自然引用用户的历史模式

两套知识配合使用：公共知识帮你理解人，私人知识帮你理解这个具体的人。
如果用户没有历史数据，只用公共知识即可——像第一次见面一样自然交流。

每次对话你在心里走四步，但用户不需要知道这四步的名字：
1. 先理解和认可用户的感受，让对方觉得被听见
2. 温和地帮用户找到情绪的根源（"这种感觉让你想到了什么？"）
3. 帮用户从不同角度看看自己的假设（引导但不强推）
4. 在对话自然结束时，帮用户整理今天的收获

对话风格：
- 自然、像朋友聊天，不要让用户觉得"被流程推着走"
- 不超过3句话，句句有用
- 不评价用户的感受（不说"你不该这么想"）
- 追问先于建议——理解清楚再引导
- 当发现话题和用户之前的对话有联系时，自然地提一句（如"这让我想起你上次也聊到过类似的事"）
- 对话结束时，用一句话总结今天的发现（"今天聊下来，我看到你……"）

输出格式：
---STRUCTURED
{"emotion_tags":["焦虑"],"emotion_intensity":4,"attribution":"和同事比较进度","stage":"attribution"}
---END

---STRUCTURED是系统要求，每次回复都必须在最后附上。
字段说明：
- emotion_tags: 识别到的情绪标签（1-3个）
- emotion_intensity: 情绪强度 1-5
- attribution: 用户归因的内容（如果有发现），没有则为""
- stage: 当前阶段 empathy / attribution / challenge / closure

界限：
- 不做诊断（不说"你可能有XX问题"）
- 如果用户自伤倾向，输出心理健康求助渠道"""

# ── Listening mode prompt: companion only, no guidance ──
SYSTEM_PROMPT_LISTENING = """你是"小绪"，一个安静、温暖的倾听伙伴。

核心规则（必须严格遵守）：
1. 你只负责倾听和陪伴，不主动追问原因，不分析归因，不给建议
2. 用户说什么你听着，简单共情即可——"嗯""我在听""我理解""是啊"
3. 禁止引导用户深入思考，禁止回溯历史模式，禁止追问
4. 每次回复不超过1-2句话，越短越好
5. 回复中不要使用比喻、不要做分析、不要给建议、不要做总结

错误示范（禁止）：
- "你觉得是什么让你有这种感觉？" → 这是追问，禁止
- "你的压力背后像背着一个看不见的包" → 这是比喻分析，禁止
- "从你的描述来看，工作上可能让你很疲惫" → 这是判断分析，禁止

正确示范（应该这样）：
- "嗯，我听到了。"
- "是啊，那确实挺难受的。"
- "我在的，你可以继续说。"
- "我理解，这种感受很真实。"

输出格式：
---STRUCTURED
{"emotion_tags":["悲伤"],"emotion_intensity":3,"stage":"empathy"}
---END

**重要：输出格式**
回复完对话文本后，在新的一行输出结构化JSON数据：

---STRUCTURED
{"emotion_tags":["悲伤"],"emotion_intensity":3,"stage":"empathy"}
---END

字段说明：
- emotion_tags: 识别到的主要情绪
- emotion_intensity: 情绪强度 1-5
- stage: 固定为 empathy

界限：
- 不做诊断（不说"你可能有XX问题"）
- 如果用户表现出严重情绪困扰，输出心理健康求助渠道"""


class ConversationAgent(BaseAgent):
    name = "conversation"

    def __init__(self):
        super().__init__()
        self._client = None
        self.add_skill(EmpathySkill())
        self.add_skill(AttributionSkill())
        self.add_skill(ChallengeSkill())
        self.add_skill(ClosureSkill())

    @property
    def client(self):
        if self._client is None:
            self._client = OpenAI(
                api_key=Config.LLM_API_KEY,
                base_url=Config.LLM_BASE_URL,
            )
        return self._client

    def _select_prompt(self, mode: str) -> str:
        if mode == "listening":
            return SYSTEM_PROMPT_LISTENING
        return SYSTEM_PROMPT_EXPLORING

    def _build_messages(self, history: list[dict], user=None, mode="exploring") -> list[dict]:
        prompt = self._select_prompt(mode)

        # Append personal knowledge base to main prompt (not as separate message)
        if mode == "exploring" and user:
            from agents.knowledge_base import PersonalKnowledgeBase
            kb = PersonalKnowledgeBase(user, max_chars=Config.KNOWLEDGE_BASE_MAX_CHARS)
            # Find the last user message to use as L3 search query
            last_user_msg = ""
            for msg in reversed(history):
                if msg.get("role") == "user":
                    last_user_msg = msg["content"]
                    break
            context_block = kb.build_system_context_block(
                mode=mode, user_input=last_user_msg
            )
            if context_block:
                prompt += context_block

        messages = [{"role": "system", "content": prompt}]
        # take last 20: recent history + current user message at the end
        messages.extend(history[-20:])
        return messages

    def _parse_response(self, raw: str) -> tuple[str, dict]:
        """Extract text and structured JSON from LLM response.

        Handles:
        1. ---STRUCTURED\n{...}\n---END
        2. ---STRUCTUR{...}  (typo/malformed marker)
        3. Any trailing JSON dict
        """
        # Find any marker-like pattern: ---STR... followed by JSON
        marker_match = re.search(r"---STR[A-Z]*", raw)
        if marker_match:
            after = raw[marker_match.end():].strip()
            # Try to extract JSON from after the marker
            brace_start = after.find("{")
            if brace_start >= 0:
                json_str = after[brace_start:]
                close_idx = json_str.find("}")
                if close_idx >= 0:
                    json_str = json_str[:close_idx + 1]
                try:
                    meta = json.loads(json_str)
                    if isinstance(meta, dict):
                        text = raw[:marker_match.start()].strip()
                        return text, meta
                except json.JSONDecodeError:
                    pass
            # Still strip everything from marker onwards
            text = raw[:marker_match.start()].strip()
            return text, {}

        # Fallback: find any trailing JSON-like block
        pattern = r"\{[^{}]*\}"
        matches = list(re.finditer(pattern, raw, re.DOTALL))
        if matches:
            last_json = matches[-1].group()
            try:
                parsed = json.loads(last_json)
                if isinstance(parsed, dict):
                    text = raw[:matches[-1].start()].strip()
                    return text, parsed
            except json.JSONDecodeError:
                pass

        text = raw.strip()
        meta = {}
        # Fallback: try LLM extraction
        if text:
            meta = self._extract_meta_via_llm(text)
        return text, meta

    def _extract_meta_via_llm(self, text: str) -> dict:
        """Fallback: use a lightweight call to extract structured data."""
        if not Config.llm_available() or len(text) < 10:
            return {}
        try:
            resp = self.client.chat.completions.create(
                model=Config.LLM_MODEL,
                messages=[{
                    "role": "system",
                    "content": "从以下回复中提取结构化数据，只输出JSON："
                               "{\"emotion_tags\":[],\"emotion_intensity\":0,\"attribution\":\"\","
                               "\"stage\":\"empathy\"}"
                }, {
                    "role": "user",
                    "content": text[:200],
                }],
                temperature=0.1,
                max_tokens=200,
            )
            raw = resp.choices[0].message.content or "{}"
            return json.loads(raw)
        except Exception:
            return {}

    def run(self, user_input: str, session_history: list[dict],
            user=None, mode="exploring") -> tuple[str, dict]:
        messages = self._build_messages(
            session_history + [{"role": "user", "content": user_input}],
            user=user,
            mode=mode,
        )

        if not Config.llm_available():
            return self._fallback_response(user_input, mode)

        try:
            resp = llm_call(
                self.client.chat.completions.create,
                model=Config.LLM_MODEL,
                messages=messages,
                temperature=Config.LLM_TEMPERATURE,
                max_tokens=Config.LLM_MAX_TOKENS,
            )
            raw = resp.choices[0].message.content or ""
            logger.info("RAW LLM RESPONSE: %s", raw[:800])
            for i, m in enumerate(messages):
                truncated = m['content'][:200] if m['content'] else ''
                logger.info("MSG %d [%s]: %s", i, m['role'], truncated)
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            raw = f"小绪暂时没法回答，休息一下再聊吧。（错误: {e}）"

        response_text, struct_meta = self._parse_response(raw)

        context = {
            "user_input": user_input,
            "response_text": response_text,
            "structured_meta": struct_meta,
        }
        if mode == "exploring":
            context = self.run_skills(context)

        return context["response_text"], context["structured_meta"]

    def run_stream(self, user_input: str, session_history: list[dict],
                   user=None, mode="exploring"):
        """Streaming version. Yields text chunks; yields (None, meta_dict) at end.

        CRITICAL: must NOT leak ---STRUCTURED {...} ---END metadata as visible text.
        Detects the structured marker during streaming and stops yielding text
        once the metadata block begins.
        """
        messages = self._build_messages(
            session_history + [{"role": "user", "content": user_input}],
            user=user,
            mode=mode,
        )

        if not Config.llm_available():
            text, meta = self._fallback_response(user_input, mode)
            yield text
            yield (None, meta)
            return

        full_raw = ""
        structured_detected = False
        pending_yield = ""
        STRUCTURED_MARKER = "---STR"

        def _is_marker_prefix(text: str) -> bool:
            """Check if text could be a partial marker."""
            if not text:
                return False
            if not text.startswith("---"):
                return False
            return STRUCTURED_MARKER.startswith(text)

        try:
            stream = llm_call(
                self.client.chat.completions.create,
                model=Config.LLM_MODEL,
                messages=messages,
                temperature=Config.LLM_TEMPERATURE,
                max_tokens=Config.LLM_MAX_TOKENS,
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if not delta:
                    continue

                full_raw += delta

                if structured_detected:
                    continue

                pending_yield += delta

                # Check marker in pending only (not full_raw — avoids re-yielding old text)
                marker_idx = pending_yield.find(STRUCTURED_MARKER)
                if marker_idx >= 0:
                    structured_detected = True
                    text_before = pending_yield[:marker_idx]
                    if text_before:
                        yield text_before
                    break

                # Hold back if pending could be a partial marker
                if _is_marker_prefix(pending_yield):
                    continue

                yield pending_yield
                pending_yield = ""

            # If marker never appeared, flush pending
            if not structured_detected and pending_yield:
                yield pending_yield
        except Exception as e:
            logger.error("LLM stream failed: %s", e)
            err = f"小绪暂时没法回答，休息一下再聊吧。（错误: {e}）"
            full_raw = err
            yield err

        # Parse metadata from full_raw (which includes the structured block)
        response_text, struct_meta = self._parse_response(full_raw)
        context = {
            "user_input": user_input,
            "response_text": response_text,
            "structured_meta": struct_meta,
        }
        if mode == "exploring":
            context = self.run_skills(context)

        yield (None, context["structured_meta"])

    def _fallback_response(self, user_input: str, mode="exploring") -> tuple[str, dict]:
        """Return a canned response when no API key is configured."""
        import random
        if mode == "listening":
            responses = [
                "嗯，我听着。",
                "能理解，我会陪着你的。",
                "我感受到了你的心情，我在的。",
                "嗯，继续说，我听着。",
            ]
            text = random.choice(responses)
            meta = {"emotion_tags": [], "emotion_intensity": 0, "stage": "empathy"}
        else:
            responses = [
                "能感受到你今天有想要聊聊的事情。你愿意多说说吗？",
                "嗯，我听着。你觉得这件事对你来说意味着什么？",
                "我理解你的感受。这种情况以前也发生过吗？",
            ]
            text = random.choice(responses)
            meta = {
                "emotion_tags": [],
                "emotion_intensity": 0,
                "stage": "empathy",
                "attribution": "",
            }
        return text, meta
