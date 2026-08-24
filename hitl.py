from langchain.messages import ToolMessage
from config import HITL_ENABLED
from logger import agent_logger

SENSITIVE_TOOLS = {
    "create_ticket",    # Creating new ticket
    "book_room",        # Creating new booking
    "cancel_booking",   # Canceling booking
    "update_ticket",    # Updating important information (bao gồm cancel qua status)
    "update_booking",   # Updating important information
}


def get_pending_action(app, config):
    """Return `(node_name, [tool_calls])` if the graph is paused awaiting approval and at least one sensitive tool requires confirmation. 
    Otherwise (if Human-in-the-Loop is disabled, or only non-sensitive tools such as `track_*` are present), 
    return `None` so the graph can continue execution immediately."""
    if not HITL_ENABLED:
        return None

    snapshot = app.get_state(config)
    if not snapshot.next:
        return None  # không có gì đang chờ

    interrupted_node = snapshot.next[0]
    last_message = snapshot.values["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", [])
    if not tool_calls:
        return None

    sensitive_calls = [tc for tc in tool_calls if tc["name"] in SENSITIVE_TOOLS]
    if not sensitive_calls:
        return None  # only non-sensitive tools -> no need to wait for approval

    return interrupted_node, sensitive_calls


def needs_auto_resume(app, config):
    """True if the graph is paused but there are NO sensitive tools requiring approval, -> resume."""
    snapshot = app.get_state(config)
    if not snapshot.next:
        return False
    last_message = snapshot.values["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", [])
    if not tool_calls:
        return False
    return not any(tc["name"] in SENSITIVE_TOOLS for tc in tool_calls)


def approve_action(app, config):
    """Allow the graph to continue - the tool will be executed."""
    thread_id = config["configurable"]["thread_id"]
    agent_logger.info(f"HITL APPROVED thread_id={thread_id}")
    return app.invoke(None, config=config)


def reject_action(app, config, interrupted_node, tool_calls, reason="User rejected executing this action."):
    """Do not execute the tool - inject a ToolMessage 'rejected' for each tool_call."""
    thread_id = config["configurable"]["thread_id"]
    agent_logger.info(f"HITL REJECTED thread_id={thread_id} tools={[tc['name'] for tc in tool_calls]}")
    reject_messages = [
        ToolMessage(content=reason, tool_call_id=tc["id"])
        for tc in tool_calls
    ]
    app.update_state(config, {"messages": reject_messages}, as_node=interrupted_node)
    return app.invoke(None, config=config)