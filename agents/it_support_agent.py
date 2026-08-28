from langchain_core.messages import SystemMessage
from langgraph.prebuilt import ToolNode

from services.ai_adapter import get_chat_llm
from state import AgentState
from tools.search_tool import search_with_cache
from utils.llm_retry import invoke_with_retry
from logger import agent_logger

IT_SUPPORT_TOOLS = [search_with_cache]
it_tool_node = ToolNode(IT_SUPPORT_TOOLS)

IT_SUPPORT_SYSTEM_PROMPT = (
    "You are an IT Support Agent helping with technical issues on computers "
    "and electronic devices.\n"
    "- Use the search tool for troubleshooting guides from reliable sources.\n"
    "- Support both Vietnamese and English.\n"
    "- Give practical, easy-to-understand solutions with reference links if available."
)


def it_support_agent_node(state: AgentState) -> dict:
    memory_context = state.get("retrieved_memory", "")
    llm_with_tools = get_chat_llm().bind_tools(IT_SUPPORT_TOOLS)

    messages = state["messages"]
    if not any(isinstance(m, SystemMessage) for m in messages):
        system_content = IT_SUPPORT_SYSTEM_PROMPT
        if memory_context:
            system_content += f"\n\n{memory_context}"
        messages = [SystemMessage(content=system_content)] + messages

    response = invoke_with_retry(llm_with_tools, messages)

    tool_calls = getattr(response, "tool_calls", None)
    if tool_calls:
        agent_logger.info(f"IT_SUPPORT_AGENT calling tools={[tc['name'] for tc in tool_calls]}")
    else:
        agent_logger.info(f"IT_SUPPORT_AGENT response={response.content[:200]!r}")

    return {"messages": [response]}


def it_support_should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "end"