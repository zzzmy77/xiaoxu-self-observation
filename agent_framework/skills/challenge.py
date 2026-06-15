"""Challenge skill: detect absolutist language in user input."""
from agent_framework.base import BaseSkill


ABSOLUTIST_PATTERNS = ["总是", "从来", "永远", "每次", "从不", "每次都", "没人", "所有人"]


class ChallengeSkill(BaseSkill):
    name = "challenge"

    def apply(self, context: dict) -> dict:
        user_input = context.get("user_input", "")
        meta = context.get("structured_meta", {})
        found = [p for p in ABSOLUTIST_PATTERNS if p in user_input]
        if found:
            meta["absolutist_detected"] = found
        context["structured_meta"] = meta
        return context
