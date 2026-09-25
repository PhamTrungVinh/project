from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.prebuilt import ToolNode

from services.ai_adapter import get_chat_llm
from services.date_service import get_current_datetime_str
from state import AgentState
from shared_platform.auth_claims import AuthClaims
from services.ticket_service import build_chat_tools
from utils.llm_retry import invoke_with_retry
from logger import agent_logger
from confirmation import (
    SENSITIVE_TOOLS,
    build_confirmation_question,
    build_confirmation_response,
    completed_results_for_current_request,
)
from tasks import DEFAULT_TTL_SECONDS, add_task
from database import get_db_session
from services import pending_action_service

TICKET_SYSTEM_PROMPT_TEMPLATE = (
    "You are a Ticket Support Agent handling create/track/update ticket requests.\n"
    "Current date and time: {current_datetime}.\n"
    "\n"
    "The ONLY fields that exist for a ticket are: content (required), description "
    "(required), customer_name (optional), customer_phone (optional), email (optional).\n"
    "There is NO priority field, NO tags field, NO department field, and NO category "
    "field - NEVER ask about or mention these, they do not exist in this system.\n"
    "\n"
    "- To create a ticket, ask ONLY for 'content' (a short summary) and 'description' "
    "(more detail) if missing. Do not ask for anything else unless the user brings it up.\n"
    "- DO NOT ask for the user's email - it is auto-injected from context if available.\n"
    "- New tickets always start with status 'Pending'.\n"
    "- To track a ticket, only ticket_code is required.\n"
    "- Only update fields the user explicitly provides.\n"
    "- Cannot update a ticket already 'Finished' or 'Canceled'.\n"
    "- After a tool successfully completes the request, STOP calling tools."
)


def ticket_agent_node(state: AgentState) -> dict:
    owner_id = int(state["user_name"])
    thread_id = state.get("thread_id", "unknown")
    memory_context = state.get("retrieved_memory", "")
    current_datetime = state.get("current_datetime") or get_current_datetime_str()
    claims = AuthClaims(subject_id=owner_id, full_name=state.get("customer_name"), email=state.get("user_email"))
    active_request = state.get("active_request") or ""

    tools = build_chat_tools(owner_id, thread_id, claims=claims)
    llm_with_tools = get_chat_llm().bind_tools(tools)

    messages = state["messages"]
    if not any(isinstance(m, SystemMessage) for m in messages):
        system_content = TICKET_SYSTEM_PROMPT_TEMPLATE.format(current_datetime=current_datetime)
        if active_request:
            system_content += (
                "\n\nActive parent request: " + active_request
                + "\nComplete only the ticket work in this request. Do not create, update, cancel, or ask for details about bookings. Do not mention bookings in your reply; the supervisor handles the other requested work."
            )
        if memory_context:
            system_content += f"\n\n{memory_context}"
        messages = [SystemMessage(content=system_content)] + messages

    response = invoke_with_retry(llm_with_tools, messages)

    tool_calls = getattr(response, "tool_calls", None)
    if tool_calls:
        agent_logger.info(f"TICKET_AGENT calling tools={[tc['name'] for tc in tool_calls]}")
        return {"messages": [response]}

    agent_logger.info("ticket_agent_response_completed")
    return {"messages": [response]}


def ticket_should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    tool_calls = getattr(last, "tool_calls", None)
    if not tool_calls:
        return "end"
    if any(tc["name"] in SENSITIVE_TOOLS for tc in tool_calls):
        return "confirm"
    return "tools"


def ticket_confirm_node(state: AgentState) -> dict:
    """Hold sensitive tools for user confirmation instead of executing them.
    Save the tool call in unfinished_tasks for the router to process next turn."""
    last = state["messages"][-1]
    sensitive_calls = [tc for tc in last.tool_calls if tc["name"] in SENSITIVE_TOOLS]

    question = build_confirmation_question(sensitive_calls)
    response = build_confirmation_response(
        sensitive_calls, completed_results_for_current_request(state["messages"])
    )
    owner_id = int(state["user_name"])
    thread_id = state.get("thread_id", "unknown")
    with get_db_session() as db:
        pending_action = pending_action_service.create(
            db, owner_id, thread_id, "ticket", sensitive_calls[0], question, DEFAULT_TTL_SECONDS,
            request_context={key: state.get(key) for key in (
                "active_request", "requested_routes", "completed_routes",
                "agent_responses", "hop_count", "last_completed_agent",
            )},
        )
    tasks = add_task(
        state.get("unfinished_tasks", []),
        agent="ticket",
        question=question,
        task_type="confirmation",
        tool_call=sensitive_calls[0],
    )
    tasks[0]["pending_action_id"] = pending_action.id
    agent_logger.info(f"TICKET_CONFIRM asking confirmation for {sensitive_calls[0]['name']}")
    return {"messages": [AIMessage(content=response)], "unfinished_tasks": tasks}


def ticket_tools_node(state: AgentState) -> dict:
    """Run only non-sensitive tools (track_ticket); sensitive tools are held
    by ticket_confirm_node."""
    owner_id = int(state["user_name"])
    thread_id = state.get("thread_id", "unknown")
    claims = AuthClaims(subject_id=owner_id, full_name=state.get("customer_name"), email=state.get("user_email"))
    tool_node = ToolNode(build_chat_tools(owner_id, thread_id, claims=claims))
    return tool_node.invoke(state)
