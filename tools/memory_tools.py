# tools/memory_tools.py
from langchain_core.tools import tool

from services.memory_service import remember_fact as _remember_fact
from database import get_db_session


def build_memory_tools(owner_id: int) -> list:
    @tool
    def remember_fact(fact: str) -> str:
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
        with get_db_session() as db:
            _remember_fact(db, owner_id, fact)
        return f"Remembered: {fact}"

    return [remember_fact]