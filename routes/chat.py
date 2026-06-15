"""Chat routes — main dialogue interface."""
import logging
from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user, login_required

logger = logging.getLogger(__name__)

from app import db
from models.session import Session
from models.message import Message
from agent_framework.registry import AgentRegistry
from agent_framework.orchestrator import Orchestrator
from agents.conversation_agent import ConversationAgent
from agents.memory_agent import MemoryAgent
from agents.insight_agent import InsightAgent
from agents.diary_agent import DiaryAgent

chat_bp = Blueprint("chat", __name__, url_prefix="/chat")

# Initialize agents once
_registry = AgentRegistry()
_registry.register(ConversationAgent())
_registry.register(MemoryAgent())
_registry.register(InsightAgent())
_registry.register(DiaryAgent())
_orchestrator = Orchestrator(_registry)


def _get_or_create_session(user):
    """Return the latest active session or create a new one.

    Fix: explicitly order by created_at DESC so we always get
    the actual current session, not a stale one.
    """
    session = (Session.query
               .filter_by(user_id=user.id, active=True)
               .order_by(Session.created_at.desc())
               .first())
    if not session:
        session = Session(
            user_id=user.id,
            mode=user.settings.get("mode", "exploring"),
            summary={},
        )
        db.session.add(session)
        db.session.commit()
    return session


@chat_bp.route("/")
@login_required
def index():
    user = current_user
    current_session = _get_or_create_session(user)
    # Use no limit for UI rendering so all messages display,
    # instead of being cut off at 30 (which drops newer messages).
    history = current_session.get_history(limit=None)

    # Check for proactive message (only when conversation is fresh / empty)
    proactive_msg = None
    if len(history) < 2:
        try:
            from agents.knowledge_base import PersonalKnowledgeBase
            kb = PersonalKnowledgeBase(user)
            proactive_msg = kb.get_proactive_message()
        except Exception:
            pass

    return render_template(
        "chat.html", user=user, session=current_session,
        history=history, proactive_msg=proactive_msg
    )


@chat_bp.route("/api/send", methods=["POST"])
@login_required
def send_message():
    user = current_user
    current_session = _get_or_create_session(user)
    data = request.get_json() or {}
    message = data.get("message", "").strip()
    stream = data.get("stream", False)

    if not message:
        return jsonify({"error": "消息不能为空"}), 400

    if stream:
        return _send_message_stream(message, current_session, user)

    # Non-streaming (original)
    result = _orchestrator.process_message(message, current_session, user)

    # Track analytics for non-streaming path
    meta = result.get("structured_meta") or {}
    try:
        from utils.analytics_tracker import track_turn
        track_turn(user.id, current_session.id, message, meta)
    except Exception:
        pass

    return jsonify({
        "response": result["response"],
        "structured_meta": result["structured_meta"],
        "insight": result["insight"],
        "session_id": current_session.id,
        "history_endpoint": f"/chat/api/session/{current_session.id}/messages",
    })


def _send_message_stream(message, session, user):
    """Streaming SSE response.

    Fix: save user message IMMEDIATELY before streaming starts,
    so it survives page refresh even if the connection drops midway.
    """
    from flask import Response, stream_with_context
    import json

    # ── Save user message right now, before any streaming ──
    # This ensures the user's words persist even if:
    #   - the LLM stream fails mid-way
    #   - the user refreshes the page before streaming completes
    #   - the network connection drops
    user_msg = session.add_message(role="user", content=message)
    db.session.commit()

    # Track analytics for user message
    from models.analytics import AnalyticsEvent
    db.session.add(AnalyticsEvent(
        user_id=user.id, session_id=session.id,
        event_name="send_message",
        properties={"length": len(message), "mode": session.mode},
    ))
    db.session.commit()

    def _sse(event_type, data):
        """Yield a single SSE event. Escape newlines in text content for line-based parsing."""
        if event_type == "text":
            # Escape literal newlines so SSE line-splitting doesn't break JSON
            payload = data.replace('\n', '\\n').replace('\r', '\\r')
        else:
            payload = data
        yield f"data: {json.dumps({'type': event_type, 'content': payload}, ensure_ascii=False)}\n\n"

    def generate():
        # Send session_id first so frontend can use it for analysis
        yield f"data: {json.dumps({'type': 'session_id', 'content': session.id}, ensure_ascii=False)}\
\
"
        full_response = ""
        struct_meta = None
        try:
            for event_type, data in _orchestrator.process_message_stream(message, session, user):
                if event_type == "text":
                    full_response += data
                elif event_type == "meta":
                    struct_meta = data  # save meta for post-stream save
                yield from _sse(event_type, data)
        except Exception as e:
            logger.error("Stream error: %s", e)
            yield from _sse("error", str(e))
        finally:
            # ── Save assistant message after streaming completes ──
            # The user message is already saved above, so only save assistant.
            if full_response or struct_meta is not None:
                try:
                    import re as _re
                    response_text = full_response or "小绪已收到你的消息"
                    # Belt-and-suspenders: strip any remaining structured metadata
                    response_text = _re.sub(r'---STR[A-Z]*[\s\S]*?(?:---END|$)', '', response_text).strip()
                    meta = struct_meta if isinstance(struct_meta, dict) else {}

                    session.add_message(
                        role="assistant",
                        content=response_text,
                        structured_meta=meta,
                    )

                    # Update user profile
                    profile = user.profile or {}
                    emotion_freq = profile.get("emotion_frequencies", {})
                    for tag in (meta.get("emotion_tags") or []):
                        emotion_freq[tag] = emotion_freq.get(tag, 0) + 1
                    profile["emotion_frequencies"] = emotion_freq
                    user.profile = profile

                    # Track ai_reply analytics
                    db.session.add(AnalyticsEvent(
                        user_id=user.id, session_id=session.id,
                        event_name="ai_reply",
                        properties={
                            "emotion_count": len(meta.get("emotion_tags", [])),
                            "stage": meta.get("stage", ""),
                            "has_attribution": bool(meta.get("attribution", "")),
                        },
                    ))

                    db.session.commit()
                except Exception as e:
                    logger.error("Failed to save assistant message: %s", e)
                    db.session.rollback()

            # ── Unified analysis: one LLM call for both Insight (DB) + L2 display (SSE) ──
            if struct_meta and isinstance(struct_meta, dict):
                stage = struct_meta.get("stage", "")
                history = session.get_history(limit=None)
                turn_count = len(history) // 2
                should_analyze = (
                    session.mode == "exploring"
                    and (stage == "closure" or turn_count >= 3)
                )
                if should_analyze:
                    try:
                        from agents.unified_analysis import UnifiedAnalysisAgent
                        agent = UnifiedAnalysisAgent()
                        analysis = agent.analyze(session, user, struct_meta)
                        if analysis and (analysis.get("emotion_summary")
                                         or analysis.get("pattern_match")
                                         or analysis.get("actionable_tip")):
                            yield from _sse("analysis", analysis)
                    except Exception as e:
                        logger.warning("Unified analysis failed: %s", e)

            yield from _sse("done", "")

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@chat_bp.route("/api/session/<int:session_id>/messages")
@login_required
def get_messages(session_id):
    session = Session.query.get_or_404(session_id)
    msgs = session.get_all_messages()
    return jsonify([m.to_dict() for m in msgs])


@chat_bp.route("/api/new", methods=["POST"])
@login_required
def new_session():
    """Start a new conversation session."""
    user = current_user

    # Deactivate ALL active sessions for this user to avoid stale duplicates
    active_sessions = Session.query.filter_by(user_id=user.id, active=True).all()
    for s in active_sessions:
        s.active = False

    # Update session count
    profile = user.profile or {}
    profile["total_sessions"] = profile.get("total_sessions", 0) + len(active_sessions)
    user.profile = profile

    # Create new
    session = Session(user_id=user.id, mode=user.settings.get("mode", "exploring"), summary={})
    db.session.add(session)
    db.session.commit()
    return jsonify({"session_id": session.id, "redirect": "/chat"})


@chat_bp.route("/api/analyze", methods=["POST"])
@login_required
def analyze_session():
    """
    L2 条件触发：分析当前对话，返回识别结果。
    由前端在对话满3轮或 stage=closure 时调用。
    """
    user = current_user
    data = request.get_json() or {}
    session_id = data.get("session_id")

    session = Session.query.filter_by(id=session_id, user_id=user.id).first()
    if not session:
        return jsonify({"error": "Session not found"}), 404

    from agents.recognition_agent import RecognitionAgent
    agent = RecognitionAgent()
    result = agent.analyze(session, user)

    # 异步触发 L3 跨会话模式匹配（对话结束后的延迟分析）
    if result.get("emotion_summary"):
        import threading
        def _delayed_match():
            import time
            time.sleep(3)
            with db.session.no_autoflush:
                try:
                    agent.match_pattern(user)
                except Exception as e:
                    logger.warning("Pattern match error: %s", e)
        threading.Thread(target=_delayed_match, daemon=True).start()

    return jsonify(result)


@chat_bp.route("/api/mode", methods=["POST"])
@login_required
def set_mode():
    """Toggle conversation mode (exploring / listening)."""
    user = current_user
    data = request.get_json() or {}
    mode = data.get("mode", "exploring")
    if mode not in ("exploring", "listening"):
        return jsonify({"error": "无效模式"}), 400
    settings = user.settings or {}
    settings["mode"] = mode
    user.settings = settings
    # Also update current session
    current = Session.query.filter_by(user_id=user.id, active=True).first()
    if current:
        current.mode = mode
    db.session.commit()
    return jsonify({"mode": mode})
