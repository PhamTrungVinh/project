from langchain_core.messages import SystemMessage, ToolMessage
from langgraph.prebuilt import ToolNode

from services.ai_adapter import get_chat_llm
from state import AgentState
from services.it_support_service import get_chat_tools
from utils.llm_retry import invoke_with_retry
from logger import agent_logger

IT_SUPPORT_TOOLS = get_chat_tools()
it_tool_node = ToolNode(IT_SUPPORT_TOOLS)

IT_SUPPORT_SYSTEM_PROMPT = """You are a practical IT-support assistant for company users.

Style:
- Answer naturally in the user's language. Be concise by default: one short paragraph
  plus at most 3 numbered steps. Return plain text only: no asterisks, hyphen bullets,
  headings, tables, backticks, Markdown links, or formatting markers.
- Start with the most useful next action. Ask one focused clarification when it is
  needed to diagnose the problem; do not give a broad troubleshooting checklist first.
- For a laptop that beeps at startup, ask for the exact beep pattern, whether the
  screen/fans turn on, and the model/serial information before assigning a cause.

Accuracy and safety:
- Never invent vendor-specific beep codes, manuals, URLs, specifications, or test
  results. Do not state that a particular beep count means a particular component
  unless it is supported by a reliable source for that exact device.
- Use the search tool only when current or model-specific facts are needed. Prefer
  official vendor documentation. Cite only links actually returned by the tool.
- Give safe, reversible checks first. Before suggesting opening hardware, clearly
  say it is optional and recommend professional service if the user is uncomfortable
  or the device is under warranty.

Handle standalone greetings, farewells, thanks, and acknowledgements with a short,
friendly reply."""


def it_support_agent_node(state: AgentState) -> dict:
    memory_context = state.get("retrieved_memory", "")
    llm_with_tools = get_chat_llm().bind_tools(IT_SUPPORT_TOOLS)

    messages = state["messages"]
    if any(isinstance(m, ToolMessage) for m in messages):
        messages = [SystemMessage(content=IT_SUPPORT_SYSTEM_PROMPT + "\nYou already have search results for this turn. Do not call a tool again; provide the answer now.")] + messages
    elif not any(isinstance(m, SystemMessage) for m in messages):
        system_content = IT_SUPPORT_SYSTEM_PROMPT
        if memory_context:
            system_content += f"\n\n{memory_context}"
        messages = [SystemMessage(content=system_content)] + messages

    response = invoke_with_retry(llm_with_tools, messages)

    tool_calls = getattr(response, "tool_calls", None)
    if tool_calls:
        agent_logger.info(f"IT_SUPPORT_AGENT calling tools={[tc['name'] for tc in tool_calls]}")
    else:
        agent_logger.info("it_support_agent_response_completed")

    return {"messages": [response]}


def it_support_should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        if any(isinstance(m, ToolMessage) for m in state["messages"][:-1]):
            agent_logger.warning("it_support_tool_round_limit_reached")
            return "end"
        return "tools"
    if state.get("simple_pleasantry"):
        return "final"
    return "end"