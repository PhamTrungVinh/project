from langchain_core.messages import SystemMessage
from langgraph.prebuilt import ToolNode

from services.ai_adapter import get_chat_llm
from state import AgentState
from tools.search_tool import search_with_cache
from tools.calculator_tool import calculator_tool
from tools.memory_tools import build_memory_tools
from utils.llm_retry import invoke_with_retry
from logger import agent_logger

WEB_SYSTEM_PROMPT = (
    "You are a general-purpose assistant.\n"
    "- For simple factual/common-knowledge/reasoning questions you already "
    "know (basic math, well-known facts), answer DIRECTLY. Do NOT call the "
    "search tool for these.\n"
    "- Only call search_with_cache for real-time/recent info (news, prices, "
    "weather) or things you're not confident about.\n"
    "- Only call calculator_tool for complex calculations.\n"
    "- If the user asks you to remember a personal fact/preference, use remember_fact.\n"
    "- Be concise. Don't explain your internal decision process."
)


def web_agent_node(state: AgentState) -> dict:
    owner_id = int(state["user_name"])
    memory_context = state.get("retrieved_memory", "")

    tools = [search_with_cache, calculator_tool] + build_memory_tools(owner_id)
    llm_with_tools = get_chat_llm().bind_tools(tools)

    messages = state["messages"]
    if not any(isinstance(m, SystemMessage) for m in messages):
        system_content = WEB_SYSTEM_PROMPT
        if memory_context:
            system_content += f"\n\n{memory_context}"
        messages = [SystemMessage(content=system_content)] + messages

    response = invoke_with_retry(llm_with_tools, messages)

    tool_calls = getattr(response, "tool_calls", None)
    if tool_calls:
        agent_logger.info(f"WEB_AGENT calling tools={[tc['name'] for tc in tool_calls]}")
    else:
        agent_logger.info(f"WEB_AGENT response={response.content[:200]!r}")

    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "end"


def web_tools_node(state: AgentState) -> dict:
    owner_id = int(state["user_name"])
    tools = [search_with_cache, calculator_tool] + build_memory_tools(owner_id)
    tool_node = ToolNode(tools)
    return tool_node.invoke(state)