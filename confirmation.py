"""
Conversational HITL: when an agent intends to call a sensitive tool, do not run it
immediately. Ask the user for confirmation and save the tool_call in unfinished_tasks.
On the next turn, the router classifies the intent (confirm/cancel/edit). When the
user confirms, invoke the tool directly with the saved arguments so the LLM cannot
silently change them.
"""
from services.ticket_service import build_chat_tools as build_ticket_tools
from services.booking_service import build_chat_tools as build_booking_tools
from database import get_db_session
from crud.users import get_user_by_id
from services.identity_service import claims_for_user
from shared_platform.auth_claims import AuthClaims
from langchain_core.messages import HumanMessage, ToolMessage

SENSITIVE_TOOLS = {
    "create_ticket",
    "update_ticket",
    "update_ticket_status",
    "book_room",
    "update_booking",
    "cancel_booking",
}


def build_confirmation_question(tool_calls: list[dict]) -> str:
    lines = ["Before I proceed, please confirm this action:"]
    for tc in tool_calls:
        args_str = ", ".join(f"{k}={v}" for k, v in tc["args"].items() if v is not None)
        lines.append(f"- {tc['name']}({args_str})")
    lines.append("\nReply to confirm, tell me what to change, or say cancel.")
    return "\n".join(lines)


def completed_results_for_current_request(messages: list) -> list[str]:
    """Return tool results produced after the most recent user request.

    A request can require several agents. For example, ticket tracking can
    finish before a room booking pauses for approval. Only the booking should
    be pending, but the user must still see the ticket result in that reply.
    Restricting the scan to messages after the latest HumanMessage avoids
    repeating results from older turns in the conversation.
    """
    latest_human_index = next(
        (
            index for index in range(len(messages) - 1, -1, -1)
            if isinstance(messages[index], HumanMessage)
        ),
        len(messages),
    )
    return [
        str(message.content)
        for message in messages[latest_human_index + 1:]
        if isinstance(message, ToolMessage) and message.content
    ]


def build_confirmation_response(tool_calls: list[dict], completed_results: list[str]) -> str:
    """Build the visible approval response, including earlier completed work."""
    question = build_confirmation_question(tool_calls)
    if not completed_results:
        return question
    return "Completed request:\n" + "\n\n".join(completed_results) + "\n\n" + question


def _get_tool_map(agent: str, owner_id: int, thread_id: str, idempotency_key: str | None = None, claims: AuthClaims | None = None) -> dict:
    if claims is not None and claims.subject_id != owner_id:
        raise ValueError("Confirmed action owner does not match authenticated claims")
    if claims is None:
        with get_db_session() as db:
            owner = get_user_by_id(db, owner_id)
        if owner is None:
            return {}
        claims = claims_for_user(owner)

    if agent == "ticket":
        tools = build_ticket_tools(owner_id, thread_id, idempotency_key, claims)
    elif agent == "booking":
        tools = build_booking_tools(owner_id, thread_id, idempotency_key, claims)
    else:
        return {}
    return {t.name: t for t in tools}


def execute_confirmed_tool_call(agent: str, owner_id: int, thread_id: str, tool_call: dict, idempotency_key: str | None = None, *, raise_errors: bool = False, claims: AuthClaims | None = None) -> str:
    """Execute a tool call that the user confirmed through chat."""
    tool_map = _get_tool_map(agent, owner_id, thread_id, idempotency_key, claims)
    tool = tool_map.get(tool_call["name"])
    if tool is None:
        if raise_errors:
            raise ValueError(f"Tool '{tool_call['name']}' not found")
        return f"Internal error: tool '{tool_call['name']}' not found."
    try:
        return tool.invoke(tool_call["args"])
    except Exception as e:
        if raise_errors:
            raise
        return f"Error executing action: {e}"
