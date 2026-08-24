# tools/memory_tools.py (file mới)
from typing import Annotated
from langchain.tools import tool
from langgraph.prebuilt import InjectedState

from state import AgentState
from memory import save_fact

@tool
def remember_fact(fact: str, state: Annotated[AgentState, InjectedState]) -> str:
    """Save a stable, long-term fact about the user.

    Use ONLY when the information is likely to remain useful
    across future conversations.

    GOOD examples:
    - User explicitly asks to remember something.
    - User prefers concise answers.
    - User prefers Python over JavaScript.
    - User works in the Sales team.
    - User is working on a long-term project.

    DO NOT use for:
    - Current questions or requests.
    - Temporary task information.
    - Ticket details.
    - Booking details.
    - Information needed only for the current conversation.
    - One-time events.
    - Sensitive personal information.

    The fact should be short, general, and written from the user's perspective.
    """
    user_id = state.get("user_name", "anonymous")
    save_fact(user_id, fact)
    return f"Remembered: {fact}"