"""
Bridge between FastAPI (with JWT-authenticated users) and the LangGraph graph.
The graph owner_id always comes from current_user.id, never client-supplied input.
"""
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from config import MEMORY_ADAPTER
from langchain_core.messages import HumanMessage, AIMessage, AIMessageChunk
from groq import RateLimitError
from fastapi import HTTPException

from identity_service.models import User
from shared_platform.auth_claims import AuthClaims
from crud import conversation as conv_crud
from services.memory_service import build_memory_context, record_episode_async, memory_session
from services.date_service import get_current_datetime_str
from services.domain_remote_adapter import memory_context as remote_memory_context, record_memory_episode
from graph.graph import build_graph
from logger import agent_logger
from utils.presentation import to_plain_text
from services.thread_lock import thread_turn_lock
from chat_orchestrator.pending_action_model import PendingAction

_app = None


def _load_memory_context(db: Session, current_user: User | AuthClaims, message: str) -> str:
    if MEMORY_ADAPTER != "http":
        with memory_session(db) as memory_db:
            return build_memory_context(memory_db, current_user.id, message)
    try:
        return remote_memory_context(current_user, message)
    except HTTPException as exc:
        if exc.status_code < 500:
            raise
        agent_logger.warning("memory_context_unavailable status=%s", exc.status_code)
    except TimeoutError:
        agent_logger.warning("memory_context_timeout")
    return ""


def get_app():
    global _app
    if _app is None:
        _app = build_graph()
    return _app


def send_message(db: Session, current_user: User | AuthClaims, thread_id: str, message: str, *, on_delta=None) -> dict:
    with thread_turn_lock(current_user.id, thread_id):
        return _send_message_unlocked(db, current_user, thread_id, message, on_delta=on_delta)


def _send_message_unlocked(db: Session, current_user: User | AuthClaims, thread_id: str, message: str, *, on_delta=None) -> dict:
    owner_id = current_user.id
    agent_logger.info("chat_turn_started owner_id=%s thread_id=%s", owner_id, thread_id)

    conversation = conv_crud.get_or_create_conversation(db, owner_id, thread_id)
    conv_crud.set_title_if_empty(db, thread_id, message)
    conversation.updated_at = datetime.now(timezone.utc)
    db.commit()

    memory_context = _load_memory_context(db, current_user, message)
    current_datetime = get_current_datetime_str()

    app = get_app()
    config = {"configurable": {"thread_id": thread_id}}
    if on_delta is not None:
        config["configurable"]["stream_answer"] = True

    invoke_input = {
        "messages": [HumanMessage(content=message)],
        "user_name": str(owner_id),
        "customer_name": current_user.full_name,
        "user_email": current_user.email,
        "retrieved_memory": memory_context,
        "current_datetime": current_datetime,
        "thread_id": thread_id,
    }

    try:
        if on_delta is None:
            result = app.invoke(invoke_input, config=config)
        else:
            # Routing, safety decisions and tool arguments are never answer text.
            result = None
            for mode, chunk in app.stream(invoke_input, config=config, stream_mode=["messages", "custom", "values"]):
                if mode == "values":
                    result = chunk
                elif mode == "custom" and chunk.get("type") == "answer":
                    if chunk.get("text"):
                        on_delta(chunk["text"])
                elif mode == "messages":
                    message_chunk, metadata = chunk
                    if (metadata.get("langgraph_node") in {"ticket_agent", "booking_agent", "it_support_agent"}
                            and isinstance(message_chunk, AIMessageChunk)
                            and not message_chunk.tool_call_chunks and not message_chunk.tool_calls):
                        content = message_chunk.content
                        if isinstance(content, str) and content:
                            on_delta(content)
            if result is None:
                raise RuntimeError("Chat graph returned no state")
    except RateLimitError:
        agent_logger.warning(
            "chat_turn_rate_limited owner_id=%s thread_id=%s", owner_id, thread_id
        )
        return {
            "answer": (
                "The assistant is temporarily busy due to an AI provider rate limit. "
                "Please try again in a few seconds."
            ),
            "route": "",
            "thread_id": thread_id,
        }

    answer = ""
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            answer = msg.content
            break

    # Streaming clients render Markdown; retain the legacy JSON plain-text format.
    answer = str(answer or "").strip() if on_delta is not None else to_plain_text(answer)
    route = result.get("route", "")
    agent_logger.info("chat_turn_completed owner_id=%s thread_id=%s route=%s answer_present=%s", owner_id, thread_id, route, bool(answer))
    return {"answer": answer, "route": route, "thread_id": thread_id}


def continue_after_decision(db: Session, action: PendingAction) -> dict:
    """Record a decision in the checkpoint and finish the saved request.

    The caller holds the thread lock. A fixed message ID makes checkpoint replay
    safe if the process stops after graph continuation but before the answer is saved.
    """
    if action.decision_answer is not None:
        return {"answer": action.decision_answer, "route": action.decision_route}

    outcome = action.execution_result if action.status == "executed" else "Ok, I won't proceed with that action."
    app = get_app()
    config = {"configurable": {"thread_id": action.thread_id}}
    snapshot = app.get_state(config)
    if not snapshot.values:
        action.decision_answer = outcome
        action.decision_route = "confirmed"
        db.commit()
        return {"answer": outcome, "route": "confirmed"}

    marker_id = f"pending-action-decision:{action.id}"
    messages = snapshot.values.get("messages", [])
    if not any(getattr(message, "id", None) == marker_id for message in messages):
        saved_context = json.loads(action.request_context_json or "{}")
        updates = {key: value for key, value in saved_context.items() if value is not None}
        updates.update({
            "messages": [AIMessage(id=marker_id, content=outcome)],
            "route": "confirmed", "last_completed_agent": action.agent,
            "unfinished_tasks": [
                task for task in snapshot.values.get("unfinished_tasks", [])
                if task.get("pending_action_id") != action.id
            ],
        })
        app.update_state(config, updates, as_node="confirmed")
        snapshot = app.get_state(config)

    result = app.invoke(None, config=config) if snapshot.next else snapshot.values
    marker_index = next((i for i, message in enumerate(result.get("messages", []))
                         if getattr(message, "id", None) == marker_id), -1)
    following = result.get("messages", [])[marker_index + 1:] if marker_index >= 0 else []
    answer = next((to_plain_text(message.content) for message in reversed(following)
                   if isinstance(message, AIMessage) and not getattr(message, "tool_calls", None)), outcome)
    action.decision_answer = answer
    action.decision_route = result.get("route", "confirmed")
    db.commit()
    return {"answer": answer, "route": action.decision_route}


def log_task_outcome(db: Session, current_user: User, thread_id: str, summary: str, outcome: str) -> None:
    if MEMORY_ADAPTER == "http":
        record_memory_episode(current_user, thread_id, summary, outcome)
    else:
        record_episode_async(current_user.id, thread_id, summary, outcome)
    agent_logger.info("chat_task_outcome_recorded owner_id=%s thread_id=%s", current_user.id, thread_id)
