from langchain.messages import SystemMessage
from langgraph.prebuilt import ToolNode

from config import llm
from state import AgentState
from tools import ALL_TOOLS
from logger import agent_logger
from utils.llm_retry import invoke_with_retry

llm_with_tools = llm.bind_tools(ALL_TOOLS)

tool_node = ToolNode(ALL_TOOLS)


def web_agent_node(state: AgentState) -> dict:
    user_name = state.get("user_name", "User")
    memory_context = state.get("retrieved_memory", "")
    messages = state["messages"]

    if not any(isinstance(m, SystemMessage) for m in messages):
        system_content = f"You are helping {user_name}. Be friendly and concise."
        if memory_context:
            system_content += f"\n\n{memory_context}"
        messages = [SystemMessage(content=system_content)] + messages

    response = invoke_with_retry(llm_with_tools, messages) 

    tool_calls = getattr(response, "tool_calls", None)
    if tool_calls:
        agent_logger.info(
            f"WEB_AGENT calling tools={[tc['name'] for tc in tool_calls]} args={[tc['args'] for tc in tool_calls]}"
        )
    else:
        agent_logger.info(f"WEB_AGENT response={response.content[:200]!r}")

    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "end"
