from langchain.messages import SystemMessage
from langgraph.prebuilt import ToolNode

from config import llm
from state import AgentState
from tools import BOOKING_TOOLS
from logger import agent_logger
from utils.llm_retry import invoke_with_retry

llm_with_booking_tools = llm.bind_tools(BOOKING_TOOLS)
booking_tool_node = ToolNode(BOOKING_TOOLS)

def build_booking_system_prompt(current_datetime: str) -> str:
    return(
        "You are a Booking Agent responsible for booking, tracking, updating, and canceling meeting rooms.\n"
        f"Current date and time: {current_datetime}.\n"
        f"When the user says relative time expressions like 'tomorrow', 'next Monday', "
        f"'in 2 hours', 'this afternoon', etc., convert them to an ABSOLUTE date/time "
        f"before calling any tool. Always store the 'time' field as a clear, "
        f"unambiguous absolute date and time, never a relative phrase.\n"
        "- When creating a new booking, both 'reason' (booking purpose) and 'time' (scheduled time) are required. "
        "If the user has not provided either of them, ask for the missing information.\n"
        "- DO NOT ask for the user's email—the system will automatically retrieve it from the context if available.\n"
        "- Every new booking must have the status 'Scheduled'.\n"
        "- To track a booking, only the booking_id is required.\n"
        "- When updating a booking, only modify the fields explicitly provided by the user.\n"
        "- A booking can only be canceled if its status is not 'Finished'.\n"
        "- After a tool successfully completes the user's requested action, STOP calling tools."
        "- Do NOT call additional tools just to verify the result."
        "- Call exactly one tool whenever possible."
    )


def booking_agent_node(state: AgentState) -> dict:
    memory_context = state.get("retrieved_memory", "")
    current_datetime = state.get("current_datetime", "unknown")
    messages = state["messages"]
    if not any(isinstance(m, SystemMessage) for m in messages):
        system_content = build_booking_system_prompt(current_datetime)
        if memory_context:
            system_content += f"\n\n{memory_context}"
        messages = [SystemMessage(content=system_content)] + messages

    response = invoke_with_retry(llm_with_booking_tools, messages)
    # print(response.tool_calls) 

    tool_calls = getattr(response, "tool_calls", None)
    if tool_calls:
        agent_logger.info(
            f"BOOKING_AGENT calling tools={[tc['name'] for tc in tool_calls]} args={[tc['args'] for tc in tool_calls]}"
        )
    else:
        agent_logger.info(f"BOOKING_AGENT response={response.content[:200]!r}")

    return {"messages": [response]}


def booking_should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "end"
