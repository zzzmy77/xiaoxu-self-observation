"""
Standalone analytics tracker — decoupled from MemoryAgent.

Provides a single function `track_turn()` that the chat route handler
calls directly. MemoryAgent no longer owns analytics logic.
"""
import logging
from models.analytics import AnalyticsEvent

logger = logging.getLogger(__name__)


def track_turn(user_id: int, session_id: int,
               user_input: str, meta: dict) -> None:
    """Record analytics events for one conversation turn.

    Call this from the chat route handler (streaming or non-streaming)
    instead of routing through MemoryAgent.
    """
    from app import db

    try:
        # send_message event
        db.session.add(AnalyticsEvent(
            user_id=user_id, session_id=session_id,
            event_name="send_message",
            properties={"length": len(user_input), "mode": meta.get("mode", "")},
        ))

        # ai_reply event
        db.session.add(AnalyticsEvent(
            user_id=user_id, session_id=session_id,
            event_name="ai_reply",
            properties={
                "emotion_count": len(meta.get("emotion_tags", [])),
                "stage": meta.get("stage", ""),
                "has_attribution": bool(meta.get("attribution", "")),
            },
        ))

        # causal_mention event (when attribution is detected)
        attribution = meta.get("attribution", "")
        if attribution and len(attribution) > 5:
            db.session.add(AnalyticsEvent(
                user_id=user_id, session_id=session_id,
                event_name="causal_mention",
                properties={"attribution": attribution[:60]},
            ))

        db.session.commit()
    except Exception as e:
        logger.warning("Analytics track_turn failed: %s", e)
