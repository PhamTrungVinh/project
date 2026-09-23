"""
Bridge between FastAPI (with JWT-authenticated users) and the LangGraph graph.
The graph owner_id always comes from current_user.id, never client-supplied input.
"""
from sqlalchemy.orm import Session
from config import MEMORY_ADAPTER
from langchain_core.messages import HumanMessage, AIMessage
from groq import RateLimitError

from models.user import User
from crud import conversation as conv_crud
from services.memory_service import build_memory_context, record_episode_async
from services.date_service import get_current_datetime_str
from services.domain_remote_adapter import memory_context as remote_memory_context, record_memory_episode
from graph.graph import build_graph
from logger import agent_logger
from utils.presentation import to_plain_text

_app = None


def get_app():
    global _app
    if _app is None:
        _app = build_graph()
    return _app


def send_message(db: Session, current_user: User, thread_id: str, message: str) -> dict:
    owner_id = current_user.id
    agent_logger.info("chat_turn_started owner_id=%s thread_id=%s", owner_id, thread_id)

    conversation = conv_crud.get_or_create_conversation(db, owner_id, thread_id)
    conv_crud.set_title_if_empty(db, thread_id, message)

    memory_context = (
        remote_memory_context(current_user, message)
        if MEMORY_ADAPTER == "http"
        else build_memory_context(db, owner_id, message)
    )
    current_datetime = get_current_datetime_str()

    app = get_app()
    config = {"configurable": {"thread_id": thread_id}}

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
        result = app.invoke(invoke_input, config=config)
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

    answer = to_plain_text(answer)
    route = result.get("route", "")
    agent_logger.info("chat_turn_completed owner_id=%s thread_id=%s route=%s answer_present=%s", owner_id, thread_id, route, bool(answer))
    return {"answer": answer, "route": route, "thread_id": thread_id}


def log_task_outcome(db: Session, current_user: User, thread_id: str, summary: str, outcome: str) -> None:
    if MEMORY_ADAPTER == "http":
        record_memory_episode(current_user, thread_id, summary, outcome)
    else:
        record_episode_async(current_user.id, thread_id, summary, outcome)
    agent_logger.info("chat_task_outcome_recorded owner_id=%s thread_id=%s", current_user.id, thread_id)