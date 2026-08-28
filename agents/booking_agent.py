from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.prebuilt import ToolNode

from services.ai_adapter import get_chat_llm
from services.date_service import get_current_datetime_str
from state import AgentState
from tools.booking_tools import build_booking_tools
from utils.llm_retry import invoke_with_retry
from logger import agent_logger
from confirmation import SENSITIVE_TOOLS, build_confirmation_question
from tasks import add_task

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

    tools = build_booking_tools(owner_id, thread_id)
    llm_with_tools = get_chat_llm().bind_tools(tools)

    messages = state["messages"]
    if not any(isinstance(m, SystemMessage) for m in messages):
        system_content = BOOKING_SYSTEM_PROMPT_TEMPLATE.format(current_datetime=current_datetime)
        if memory_context:
            system_content += f"\n\n{memory_context}"
        messages = [SystemMessage(content=system_content)] + messages

    response = invoke_with_retry(llm_with_tools, messages)

    tool_calls = getattr(response, "tool_calls", None)
    if tool_calls:
        agent_logger.info(f"BOOKING_AGENT calling tools={[tc['name'] for tc in tool_calls]}")
    else:
        agent_logger.info(f"BOOKING_AGENT response={response.content[:200]!r}")

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
    tasks = add_task(
        state.get("unfinished_tasks", []),
        agent="booking",
        question=question,
        task_type="confirmation",
        tool_call=sensitive_calls[0],
    )
    agent_logger.info(f"BOOKING_CONFIRM asking confirmation for {sensitive_calls[0]['name']}")
    return {"messages": [AIMessage(content=question)], "unfinished_tasks": tasks}


def booking_tools_node(state: AgentState) -> dict:
    owner_id = int(state["user_name"])
    thread_id = state.get("thread_id", "unknown")
    tool_node = ToolNode(build_booking_tools(owner_id, thread_id))
    return tool_node.invoke(state)