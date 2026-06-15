"""Attribution skill: validate attribution data."""
from agent_framework.base import BaseSkill


class AttributionSkill(BaseSkill):
    name = "attribution"

    def apply(self, context: dict) -> dict:
        meta = context.get("structured_meta", {})
        stage = meta.get("stage", "")
        if stage == "attribution":
            attribution = meta.get("attribution", "")
            if not attribution:
                meta["_warnings"] = meta.get("_warnings", []) + [
                    "No attribution detected in attribution stage"
                ]
            if len(attribution) < 5:
                meta["_warnings"] = meta.get("_warnings", []) + [
                    "Attribution is too short to be meaningful"
                ]
        context["structured_meta"] = meta
        return context
