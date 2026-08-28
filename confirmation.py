"""
HITL hội thoại: khi agent định gọi 1 tool nhạy cảm, KHÔNG thực thi ngay -
thay vào đó hỏi lại user qua chat, lưu tool_call vào unfinished_tasks (loại
"confirmation"). Turn sau, router phân loại ý định user (confirm/cancel/edit)
và xử lý tương ứng. Khi user đồng ý, tool được gọi TRỰC TIẾP bằng args đã lưu
- không đưa qua LLM quyết định lại, tránh model tự đổi args ngoài ý muốn.
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
    """Thực thi trực tiếp 1 tool_call đã được user xác nhận qua chat."""
    tool_map = _get_tool_map(agent, owner_id, thread_id)
    tool = tool_map.get(tool_call["name"])
    if tool is None:
        return f"Internal error: tool '{tool_call['name']}' not found."
    try:
        return tool.invoke(tool_call["args"])
    except Exception as e:
        return f"Error executing action: {e}"