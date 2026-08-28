"""
Cầu nối giữa FastAPI (đã xác thực user qua JWT) và graph LangGraph.
owner_id truyền vào graph LUÔN lấy từ current_user.id, không bao giờ từ
input client tự gửi lên.
"""
from sqlalchemy.orm import Session
from langchain_core.messages import HumanMessage, AIMessage

from models.user import User
from crud import conversation as conv_crud
from services.memory_service import build_memory_context, remember_episode
from services.date_service import get_current_datetime_str
from graph.graph import build_graph

_app = None


def get_app():
    global _app
    if _app is None:
        _app = build_graph()
    return _app


def send_message(db: Session, current_user: User, thread_id: str, message: str) -> dict:
    owner_id = current_user.id

    conversation = conv_crud.get_or_create_conversation(db, owner_id, thread_id)
    conv_crud.set_title_if_empty(db, thread_id, message)

    memory_context = build_memory_context(db, owner_id, message)
    current_datetime = get_current_datetime_str()

    app = get_app()
    config = {"configurable": {"thread_id": thread_id}}

    invoke_input = {
        "messages": [HumanMessage(content=message)],
        "user_name": str(owner_id),
        "user_email": conversation.email,
        "retrieved_memory": memory_context,
        "current_datetime": current_datetime,
        "thread_id": thread_id,
    }

    result = app.invoke(invoke_input, config=config)

    answer = ""
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            answer = msg.content
            break

    return {"answer": answer, "route": result.get("route", ""), "thread_id": thread_id}


def log_task_outcome(db: Session, current_user: User, thread_id: str, summary: str, outcome: str) -> None:
    remember_episode(db, current_user.id, thread_id, summary, outcome)