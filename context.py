import re
from langchain_core.runnables import RunnableConfig
from state import AgentState
from datetime import datetime
from zoneinfo import ZoneInfo
from database import get_db_session
from crud import conversation as conv_crud
from logger import agent_logger

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")


def extract_email(text: str) -> str | None:
    match = EMAIL_REGEX.search(text or "")
    return match.group(0) if match else None


def context_node(state: AgentState, config: RunnableConfig) -> dict:
    """Automatically detect and update the email address from the user's latest message.
  - If a new email address is found in the message, update (overwrite) `user_email` and synchronize it with the `conversation_context` table.
  - If no email address is found, keep the existing `user_email` unchanged (do not return this key to avoid overwriting the current state with `None`)."""
    last_message = state["messages"][-1]
    text = getattr(last_message, "content", "")

    now = datetime.now(TIMEZONE)
    result = {
        "current_datetime": now.strftime("%Y-%m-%d %H:%M:%S %A"),  # always update this value, unlike email
    }

    email = extract_email(text)
    if email:
        thread_id = state.get("thread_id")
        if thread_id:
            with get_db_session() as db:
                conv_crud.update_conversation_email(db, thread_id, email)
            agent_logger.info("conversation_email_context_updated thread_id=%s", thread_id)
        result["user_email"] = email

    return result