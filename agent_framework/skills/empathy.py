"""Empathy skill: validate the empathy stage of a conversation turn."""
from agent_framework.base import BaseSkill


class EmpathySkill(BaseSkill):
    name = "empathy"

    def apply(self, context: dict) -> dict:
        meta = context.get("structured_meta", {})
        stage = meta.get("stage", "")
        if stage == "empathy":
            emotions = meta.get("emotion_tags", [])
            if not emotions:
                meta["_warnings"] = meta.get("_warnings", []) + ["No emotion tags in empathy stage"]
        context["structured_meta"] = meta
        return context
