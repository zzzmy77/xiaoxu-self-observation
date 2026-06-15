"""Agent framework: BaseAgent, BaseSkill, Registry, Orchestrator."""
import json
import logging
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)


class BaseSkill(ABC):
    """A single capability unit. Each skill produces structured context."""
    name: str = "base_skill"

    @abstractmethod
    def apply(self, context: dict) -> dict:
        """Mutate context dict and return it."""
        ...


class BaseAgent(ABC):
    """An agent is a named entity with a role prompt and a list of skills."""
    name: str = "base_agent"
    system_prompt: str = ""

    def __init__(self):
        self.skills: list[BaseSkill] = []
        self._context: dict = {}

    def add_skill(self, skill: BaseSkill):
        self.skills.append(skill)

    def set_context(self, key: str, value):
        self._context[key] = value

    def get_context(self, key: str, default=None):
        return self._context.get(key, default)

    def run_skills(self, context: dict) -> dict:
        for skill in self.skills:
            try:
                context = skill.apply(context)
            except Exception as e:
                logger.warning("Skill %s error: %s", skill.name, e)
        return context

    def run(self, user_input: str = "", session_history: list[dict] | None = None) -> tuple[str, dict]:
        """Return (response_text, structured_metadata). Override in subclasses."""
        return "", {}


class AgentRegistry:
    """Central registry of all agents."""
    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent):
        self._agents[agent.name] = agent
        logger.info("Registered agent: %s", agent.name)

    def get(self, name: str) -> Optional[BaseAgent]:
        return self._agents.get(name)

    def list(self) -> list[str]:
        return list(self._agents.keys())


class Orchestrator:
    """Routes messages through agents.

    Phase 1 flow:
      1. ConversationAgent processes user input
      2. MemoryAgent stores results
      3. If session ends → InsightAgent generates summary
    """
    def __init__(self, registry: AgentRegistry):
        self.registry = registry

    def process_message(self, user_input: str, session, user) -> dict:
        """Main entry point: message → agents → structured result."""
        # Use reverse order so LLM context has the MOST recent messages,
        # not the oldest 30 which misses today's conversations.
        history = session.get_history(reverse=True, limit=30)

        conv_agent = self.registry.get("conversation")
        response_text, struct_meta = conv_agent.run(
            user_input, history, user=user, mode=session.mode
        )

        mem_agent = self.registry.get("memory")
        context = {
            "user_input": user_input,
            "response_text": response_text,
            "structured_meta": struct_meta,
            "session": session,
            "user": user,
            "history": history,
        }
        context = mem_agent.run(context)

        # Diary generation removed: now handled by daily cron job at 2:00 AM

        return {
            "response": response_text,
            "structured_meta": struct_meta,
            "insight": None,
            "diary": None,
        }

    def process_message_stream(self, user_input: str, session, user):
        """Streaming version: yields raw text chunks, returns final result via context.

        IMPORTANT: The caller (route handler) is responsible for saving messages —
        this method only handles LLM streaming + insight generation.
        Messages are saved in _send_message_stream to avoid data loss
        if the connection drops before streaming completes.
        """
        # Use reverse order so LLM context has the MOST recent messages.
        history = session.get_history(reverse=True, limit=30)

        conv_agent = self.registry.get("conversation")

        # Stream the response text
        full_text = ""
        final_meta = None
        for item in conv_agent.run_stream(
            user_input, history, user=user, mode=session.mode
        ):
            if isinstance(item, tuple) and item[0] is None:
                final_meta = item[1]
            else:
                full_text += item
                yield ("text", item)

        response_text, struct_meta = conv_agent._parse_response(full_text)
        if final_meta:
            struct_meta = final_meta

        yield ("meta", struct_meta)
