from typing import Literal, Optional
from pydantic import BaseModel
from langchain.messages import HumanMessage, AIMessage

from config import llm
from state import AgentState
from logger import agent_logger
from tasks import add_task

MAX_HOPS = 5


class SupervisorDecision(BaseModel):
    is_done: bool
    is_waiting_for_user: bool = False
    next_route: Optional[Literal["faq", "ticket", "it_support", "booking", "web"]] = None
    final_answer: Optional[str] = None


supervisor_llm = llm.with_structured_output(SupervisorDecision, method="json_mode")

SUPERVISOR_PROMPT = """You are the Primary Assistant supervising a multi-agent system.

The user's original request:
{original_query}

Responses collected so far from specialized agents:
{agent_responses}

Decide ONE of the following three outcomes:

1. WAITING FOR USER: The latest agent response is asking the user a clarifying
   question (e.g. missing required fields like content/description/reason/time).
   -> Set is_done=true, is_waiting_for_user=true, next_route=null, final_answer=the agent's
   question verbatim (so the user sees it).
   DO NOT re-route to the same or another agent to "try again" - the agent is
   correctly waiting for missing information from the user.

2. FULLY SATISFIED: The user's entire request has been completed with concrete
   results (e.g. a ticket_id or booking_id was actually returned).
   -> Set is_done=true, is_waiting_for_user=false, next_route=null, and write a
   final_answer combining all relevant information from the agent responses.

3. NEEDS ANOTHER AGENT: A DIFFERENT capability is still needed to complete a
   DIFFERENT part of the original request (e.g. user also asked to book a room,
   which hasn't been done yet).
   -> Set is_done=false, next_route="<the different agent needed>".

Respond with a JSON object matching this schema:
{{"is_done": true, "is_waiting_for_user": true, "next_route": "ticket", "final_answer": "the question text"}}
or
{{"is_done": true, "is_waiting_for_user": false, "next_route": null, "final_answer": "combined answer"}}
or
{{"is_done": false, "is_waiting_for_user": false, "next_route": "booking", "final_answer": null}}
"""


def supervisor_node(state: AgentState) -> dict:
    hop_count = state.get("hop_count", 0)

    messages = state["messages"]
    original_query = next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)), ""
    )
    last_ai = next(
        (m.content for m in reversed(messages) if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None)),
        "",
    )

    agent_responses = state.get("agent_responses", []) + [last_ai]

    if hop_count >= MAX_HOPS:
        agent_logger.warning(f"SUPERVISOR hop_count={hop_count} >= MAX_HOPS, forcing done")
        fallback_answer = agent_responses[-1] if agent_responses else "Sorry, I couldn't complete this request."
        return {
            "route": "done", "active_agent": None, "hop_count": 0,
            "agent_responses": [], "messages": [AIMessage(content=fallback_answer)],
        }

    responses_text = "\n".join(f"- {r}" for r in agent_responses if r)

    result: SupervisorDecision = supervisor_llm.invoke(
        SUPERVISOR_PROMPT.format(original_query=original_query, agent_responses=responses_text)
    )

    # Case 1: đang chờ user cung cấp thêm info -> KẾT THÚC turn này. 
    if result.is_done and result.is_waiting_for_user:
        agent_logger.info(f"SUPERVISOR hop={hop_count} -> WAITING_FOR_USER for agent={result.next_route}")
        tasks = add_task(
            state.get("unfinished_tasks", []),
            agent=result.next_route,
            question=result.final_answer or last_ai,
        )
        return {
            "route": "done",
            "active_agent": None,         
            "hop_count": 0,
            "agent_responses": [],
            "unfinished_tasks": tasks,
            "messages": [AIMessage(content=result.final_answer or last_ai)],
        }

    # Case 2: hoàn tất thật sự
    if result.is_done:
        return {
            "route": "done", "active_agent": None, "hop_count": 0,
            "agent_responses": [],
            "messages": [AIMessage(content=result.final_answer or (agent_responses[-1] if agent_responses else ""))],
        }

    # Case 3: cần agent khác
    agent_logger.info(f"SUPERVISOR hop={hop_count} -> continue to {result.next_route}")
    return {
        "route": result.next_route, "active_agent": result.next_route,
        "hop_count": hop_count + 1, "agent_responses": agent_responses,
    }


def supervisor_decision(state: AgentState) -> str:
    mapping = {
        "faq": "rag_agent", "web": "web_agent", "ticket": "ticket_agent",
        "it_support": "it_support_agent", "booking": "booking_agent", "done": "final",
    }
    return mapping.get(state["route"], "final")