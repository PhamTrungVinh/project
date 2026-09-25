from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.prebuilt import ToolNode

from services.ai_adapter import get_chat_llm
from services.date_service import get_current_datetime_str
from state import AgentState
from shared_platform.auth_claims import AuthClaims
from services.booking_service import build_chat_tools
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

BOOKING_SYSTEM_PROMPT_TEMPLATE = (
    "You are a Booking Agent handling meeting room booking/tracking/updating/canceling.\n"
    "Current date and time: {current_datetime}.\n"
    "When the user says relative time ('tomorrow', 'next Monday', 'in 2 hours'),\n"
    "convert it to an ABSOLUTE date/time before calling any tool.\n"
    "- To book, both 'reason' and 'time' are required - ask if missing.\n"
    "- DO NOT ask for the user's email - it is auto-injected from context.\n"
    "- New bookings always start with status 'Scheduled'.\n"
    "- Only update fields the user explicitly provides.\n"
    "- After a tool successfully completes the request, STOP calling tools."
)


def booking_agent_node(state: AgentState) -> dict:
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
        system_content = BOOKING_SYSTEM_PROMPT_TEMPLATE.format(current_datetime=current_datetime)
        if active_request:
            system_content += (
                "\n\nActive parent request: " + active_request
                + "\nComplete only the booking work in this request. Do not create, update, cancel, or ask for details about tickets; the ticket agent handles those separately."
            )
        if memory_context:
            system_content += f"\n\n{memory_context}"
        messages = [SystemMessage(content=system_content)] + messages

    response = invoke_with_retry(llm_with_tools, messages)

    tool_calls = getattr(response, "tool_calls", None)
    if tool_calls:
        agent_logger.info(f"BOOKING_AGENT calling tools={[tc['name'] for tc in tool_calls]}")
    else:
        agent_logger.info("booking_agent_response_completed")

    return {"messages": [response]}


def booking_should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    tool_calls = getattr(last, "tool_calls", None)
    if not tool_calls:
        return "end"
    if any(tc["name"] in SENSITIVE_TOOLS for tc in tool_calls):
        return "confirm"
    return "tools"


def booking_confirm_node(state: AgentState) -> dict:
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
            db, owner_id, thread_id, "booking", sensitive_calls[0], question, DEFAULT_TTL_SECONDS,
            request_context={key: state.get(key) for key in (
                "active_request", "requested_routes", "completed_routes",
                "agent_responses", "hop_count", "last_completed_agent",
            )},
        )
    tasks = add_task(
        state.get("unfinished_tasks", []),
        agent="booking",
        question=question,
        task_type="confirmation",
        tool_call=sensitive_calls[0],
    )
    tasks[0]["pending_action_id"] = pending_action.id
    agent_logger.info(f"BOOKING_CONFIRM asking confirmation for {sensitive_calls[0]['name']}")
    return {"messages": [AIMessage(content=response)], "unfinished_tasks": tasks}


def booking_tools_node(state: AgentState) -> dict:
    owner_id = int(state["user_name"])
    claims = AuthClaims(subject_id=owner_id, full_name=state.get("customer_name"), email=state.get("user_email"))
    thread_id = state.get("thread_id", "unknown")
    tool_node = ToolNode(build_chat_tools(owner_id, thread_id, claims=claims))
    return tool_node.invoke(state)
