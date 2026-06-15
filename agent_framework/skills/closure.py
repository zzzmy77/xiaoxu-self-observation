"""Closure skill: ensure insight draft exists in closure stage."""
from agent_framework.base import BaseSkill


class ClosureSkill(BaseSkill):
    name = "closure"

    def apply(self, context: dict) -> dict:
        meta = context.get("structured_meta", {})
        stage = meta.get("stage", "")
        if stage == "closure":
            draft = meta.get("insight_draft", "")
            if not draft or len(draft) < 10:
                meta["_warnings"] = meta.get("_warnings", []) + [
                    "Insight draft is empty or too short"
                ]
        context["structured_meta"] = meta
        return context
