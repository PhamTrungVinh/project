from langchain.messages import SystemMessage
from langgraph.prebuilt import ToolNode

from config import llm
from state import AgentState
from tools import IT_SUPPORT_TOOLS
from logger import agent_logger
from utils.llm_retry import invoke_with_retry

llm_with_it_tools = llm.bind_tools(IT_SUPPORT_TOOLS)
it_tool_node = ToolNode(IT_SUPPORT_TOOLS)

IT_SUPPORT_SYSTEM_PROMPT = (
    "You are an IT Support Agent that helps users troubleshoot technical issues with computers and electronic devices.\n"
    "- Use the search tool (Tavily) to find troubleshooting guides and solutions.\n"
    "- Prioritize information from reputable technology sources.\n"
    "- Respond in either Vietnamese or English, depending on the language used by the user.\n"
    "- Provide practical, easy-to-understand answers with specific troubleshooting steps, and cite reference sources when available."
)


def it_support_agent_node(state: AgentState) -> dict:
    messages = state["messages"]
    memory_context = state.get("retrieved_memory", "")
    if not any(isinstance(m, SystemMessage) for m in messages):
        system_content = IT_SUPPORT_SYSTEM_PROMPT
        if memory_context:
            system_content += f"\n\n{memory_context}"
        messages = [SystemMessage(content=system_content)] + messages

    response = invoke_with_retry(llm_with_it_tools, messages)

    tool_calls = getattr(response, "tool_calls", None)
    if tool_calls:
        agent_logger.info(
            f"IT_SUPPORT_AGENT calling tools={[tc['name'] for tc in tool_calls]} args={[tc['args'] for tc in tool_calls]}"
        )
    else:
        agent_logger.info(f"IT_SUPPORT_AGENT response={response.content[:200]!r}")

    return {"messages": [response]}


def it_support_should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "end"
