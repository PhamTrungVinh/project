"""Reconstruct the user-visible transcript from an owned graph checkpoint."""

from langchain_core.messages import AIMessage, HumanMessage

from crud import conversation as conv_crud
from services.chat_service import get_app
from services.thread_lock import thread_turn_lock
from chat_orchestrator.pending_action_model import PendingAction
from logger import agent_logger
from utils.exceptions import AppException


def visible_messages(messages):
    transcript = []
    latest_reply = None
    has_user = False

    def serialize(message, role, index):
        content = message.content
        if not isinstance(content, str):
            content = "".join(block.get("text", "") for block in content
                              if isinstance(block, dict) and block.get("type") == "text")
        return {"id": message.id or f"{role}-{index}", "role": role, "text": content}

    for index, message in enumerate(messages):
        if isinstance(message, HumanMessage):
            if latest_reply is not None:
                transcript.append(latest_reply)
            transcript.append(serialize(message, "user", index))
            latest_reply = None
            has_user = True
        elif has_user and isinstance(message, AIMessage) and not message.tool_calls:
            # Only the final reply of a turn is delivered; earlier agent drafts
            # and tool results belong to the graph's internal working state.
            latest_reply = serialize(message, "assistant", index)
    if latest_reply is not None:
        transcript.append(latest_reply)
    return transcript


def get_conversation_history(db, owner_id, thread_id):
    conversation = conv_crud.get_user_conversation(db, owner_id, thread_id)
    with thread_turn_lock(owner_id, thread_id):
        snapshot = get_app().get_state({"configurable": {"thread_id": thread_id}})
    values = snapshot.values or {}
    return conversation, {
        "messages": visible_messages(values.get("messages", [])),
        "route": values.get("route", ""),
        "history_available": bool(values),
    }


def delete_conversation(db, owner_id, thread_id):
    with thread_turn_lock(owner_id, thread_id):
        conversation = conv_crud.get_user_conversation(db, owner_id, thread_id)
        try:
            # Remove the checkpoint first. If cleanup fails, retain the sidebar
            # entry so the user can retry; delete_thread is idempotent.
            get_app().checkpointer.delete_thread(thread_id)
            db.query(PendingAction).filter_by(owner_id=owner_id, thread_id=thread_id).delete(synchronize_session=False)
            db.delete(conversation)
            db.commit()
        except Exception as exc:
            db.rollback()
            agent_logger.exception("conversation_delete_failed owner_id=%s thread_id=%s", owner_id, thread_id)
            raise AppException("Unable to delete this chat. Please try again.", status_code=503) from exc
