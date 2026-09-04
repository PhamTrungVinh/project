from typing import Literal, Optional
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage

from services.ai_adapter import get_chat_llm
from state import AgentState
from logger import agent_logger
from tasks import add_task

VALID_ROUTES = {"faq", "ticket", "it_support", "booking", "web"}

MAX_HOPS = 5

SUPERVISOR_PROMPT = """You are the Primary Assistant supervising a multi-agent system.

User's original request: {original_query}
Responses collected so far: {agent_responses}

Decide ONE outcome:
1. WAITING FOR USER: latest response is asking a clarifying question (missing
   required fields). -> is_done=true, is_waiting_for_user=true,
   next_route="<the SAME agent that just responded, must be one of: faq, ticket, it_support, booking, web>",
   final_answer=<the question text>.
2. FULLY SATISFIED: entire request completed with concrete results.
   -> is_done=true, is_waiting_for_user=false, next_route=null,
   final_answer=<combined answer in natural language>.
3. NEEDS ANOTHER AGENT: a different capability is still needed.
   -> is_done=false, next_route="<the agent needed, must be one of: faq, ticket, it_support, booking, web>".

IMPORTANT: next_route must ALWAYS be one of exactly these 5 values: faq, ticket,
it_support, booking, web. NEVER use any other value like "primary" or "supervisor" -
if unsure which agent handled the last response, use "web" as a safe default.

Respond with a JSON object matching this schema:
{{"is_done": bool, "is_waiting_for_user": bool, "next_route": "<route or null>", "final_answer": "<text or null>"}}"""


class SupervisorDecision(BaseModel):
    is_done: bool
    is_waiting_for_user: bool = False
    next_route: Optional[Literal["faq", "ticket", "it_support", "booking", "web"]] = None
    final_answer: Optional[str] = None


def supervisor_node(state: AgentState) -> dict:
    hop_count = state.get("hop_count", 0)
    messages = state["messages"]

    original_query = next((m.content for m in reversed(messages) if isinstance(m, HumanMessage)), "")
    last_ai = next(
        (m.content for m in reversed(messages) if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None)), ""
    )
    agent_responses = state.get("agent_responses", []) + [last_ai]

    if hop_count >= MAX_HOPS:
        agent_logger.warning(f"SUPERVISOR hop_count={hop_count} >= MAX_HOPS, forcing done")
        fallback = agent_responses[-1] if agent_responses else "Sorry, I couldn't complete this request."
        return {"route": "done", "hop_count": 0, "agent_responses": [],
                "messages": [AIMessage(content=fallback)]}

    llm = get_chat_llm().with_structured_output(SupervisorDecision, method="json_mode")
    responses_text = "\n".join(f"- {r}" for r in agent_responses if r)

    try:
        result: SupervisorDecision = llm.invoke(
            SUPERVISOR_PROMPT.format(original_query=original_query, agent_responses=responses_text)
        )
    except Exception as e:
        # Model trả về route không hợp lệ hoặc parse lỗi -> fallback an toàn:
        # coi như đã xong, trả nguyên câu trả lời gần nhất thay vì crash cả request.
        agent_logger.warning(f"SUPERVISOR parse failed: {e}, falling back to last response")
        fallback = agent_responses[-1] if agent_responses else "Sorry, something went wrong."
        return {"route": "done", "hop_count": 0, "agent_responses": [],
                "messages": [AIMessage(content=fallback)]}

    if result.is_done and result.is_waiting_for_user:
        agent_logger.info(f"SUPERVISOR hop={hop_count} -> WAITING_FOR_USER, adding task for agent={result.next_route!r}")
        tasks = add_task(
            state.get("unfinished_tasks", []),
            agent=result.next_route,
            question=result.final_answer or last_ai,
        )
        return {"route": "done", "hop_count": 0, "agent_responses": [], "unfinished_tasks": tasks,
                "messages": [AIMessage(content=result.final_answer or last_ai)]}

    if result.is_done:
        answer = result.final_answer or (agent_responses[-1] if agent_responses else "")
        agent_logger.info(f"SUPERVISOR hop={hop_count} -> DONE")
        return {"route": "done", "hop_count": 0, "agent_responses": [],
                "messages": [AIMessage(content=answer)]}

    agent_logger.info(f"SUPERVISOR hop={hop_count} -> continue to {result.next_route}")
    return {"route": result.next_route, "hop_count": hop_count + 1, "agent_responses": agent_responses}


def supervisor_decision(state: AgentState) -> str:
    mapping = {
        "faq": "rag_agent", "web": "web_agent", "ticket": "ticket_agent",
        "it_support": "it_support_agent", "booking": "booking_agent", "done": "final",
    }
    return mapping.get(state["route"], "final")