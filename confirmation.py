"""
Conversational HITL: when an agent intends to call a sensitive tool, do not run it
immediately. Ask the user for confirmation and save the tool_call in unfinished_tasks.
On the next turn, the router classifies the intent (confirm/cancel/edit). When the
user confirms, invoke the tool directly with the saved arguments so the LLM cannot
silently change them.
"""
from tools.ticket_tools import build_ticket_tools
from tools.booking_tools import build_booking_tools

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


def _get_tool_map(agent: str, owner_id: int, thread_id: str) -> dict:
    if agent == "ticket":
        tools = build_ticket_tools(owner_id, thread_id)
    elif agent == "booking":
        tools = build_booking_tools(owner_id, thread_id)
    else:
        return {}
    return {t.name: t for t in tools}


def execute_confirmed_tool_call(agent: str, owner_id: int, thread_id: str, tool_call: dict) -> str:
    """Execute a tool call that the user confirmed through chat."""
    tool_map = _get_tool_map(agent, owner_id, thread_id)
    tool = tool_map.get(tool_call["name"])
    if tool is None:
        return f"Internal error: tool '{tool_call['name']}' not found."
    try:
        return tool.invoke(tool_call["args"])
    except Exception as e:
        return f"Error executing action: {e}"