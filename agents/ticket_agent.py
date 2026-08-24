from langchain.messages import SystemMessage
from langgraph.prebuilt import ToolNode

from config import llm
from state import AgentState
from tools import TICKET_TOOLS
from logger import agent_logger
from utils.llm_retry import invoke_with_retry

llm_with_ticket_tools = llm.bind_tools(TICKET_TOOLS)
ticket_tool_node = ToolNode(TICKET_TOOLS)

TICKET_SYSTEM_PROMPT = (
    "You are a Ticket Support Agent responsible for creating, tracking, and updating IT or customer support tickets.\n"
    "- When creating a new ticket, both 'content' and 'description' are required. If the user has not provided them, ask for the missing information.\n"
    "- DO NOT ask for the user's email, the system will automatically retrieve it from the context if available.\n"
    "- Every new ticket must have the status 'Pending'.\n"
    "- To track a ticket, only the ticket_id is required.\n"
    "- When updating a ticket, only update the fields provided by the user, keeping the rest unchanged. "
    "- Cannot update tickets that are already 'Finished' or 'Canceled'."
)


def _valid_create_ticket_call(tool_call) -> bool:
    args = tool_call.get("args", {})

    content = args.get("content")
    description = args.get("description")

    return (
        isinstance(content, str)
        and bool(content.strip())
        and isinstance(description, str)
        and bool(description.strip())
    )


def ticket_agent_node(state: AgentState) -> dict:
    messages = state["messages"]
    memory_context = state.get("retrieved_memory", "")

    if not any(isinstance(m, SystemMessage) for m in messages):
        system_content = TICKET_SYSTEM_PROMPT

        if memory_context:
            system_content += f"\n\n{memory_context}"

        messages = [SystemMessage(content=system_content)] + messages

    response = invoke_with_retry(llm_with_ticket_tools, messages)

    tool_calls = getattr(response, "tool_calls", None)

    if tool_calls:
        agent_logger.info(
            f"TICKET_AGENT calling tools="
            f"{[tc['name'] for tc in tool_calls]} "
            f"args={[tc['args'] for tc in tool_calls]}"
        )
    else:
        agent_logger.info(
            f"TICKET_AGENT response={response.content[:200]!r}"
        )

    return {"messages": [response]}


def ticket_should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "end"
