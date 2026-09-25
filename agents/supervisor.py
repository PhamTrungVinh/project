from typing import Literal, Optional
from pydantic import BaseModel, model_validator
from langchain_core.messages import HumanMessage, AIMessage

from services.ai_adapter import get_chat_llm
from state import AgentState
from logger import agent_logger
from tasks import add_task

VALID_ROUTES = {"faq", "ticket", "booking", "it_support"}

MAX_HOPS = 5

SUPERVISOR_PROMPT = """You are the Primary Assistant supervising a multi-agent system.

User's original request: {original_query}
Planned capabilities: {requested_routes}
Current capability: {current_route}
Earlier agent responses (historical; questions may already be answered):
{agent_responses}

User messages for this request, in chronological order:
{user_messages}

Replies already shown to the user in earlier turns of this request:
{delivered_replies}

Latest result from the current capability:
{latest_result}
Latest result source: {result_source}

Interpret requests and results by meaning, not keywords or a required output format.
A natural-language status report can satisfy a lookup; do not repeat it because
it lacks a particular field label. Visiting an agent does not prove completion.
Evaluate the latest result in light of the user's follow-up messages. Earlier
questions are historical, not evidence that details are still missing. A successful
confirmed action supersedes earlier questions and approval requests for that action.
Report its actual result, including its reference code. Never ask again for details
already supplied or repeat an action that succeeded. A failed action is not success:
explain the failure or route for recovery using the actual result.

Keep completion reasoning separate from what you display. Use earlier results to
decide what remains unfinished, but final_answer should report only new results
and any currently needed question. Do not repeat details already shown in earlier
turns unless the user explicitly asks for a recap or those details have changed.
Results produced by multiple agents during THIS turn have not yet been shown:
include all of those new results. After a confirmation, normally report the new
action's outcome and reference code without restating earlier lookup details.

Decide ONE outcome:
1. WAITING FOR USER: the LATEST result is asking a clarifying question (missing
   required fields). -> is_done=true, is_waiting_for_user=true,
   next_route="<the SAME agent that just responded, must be one of: faq, ticket, booking, it_support>",
   final_answer=<new results not previously shown plus the question text>.
2. FULLY SATISFIED: entire request completed with concrete results.
   -> is_done=true, is_waiting_for_user=false, next_route=null,
   final_answer=<new results not previously shown, in natural language>.
3. NEEDS MORE WORK: any requested outcome is still incomplete.
   -> is_done=false, next_route="<the agent needed, must be one of: faq, ticket, booking, it_support>".

A remaining action MAY require the SAME agent that produced the latest response.
Break the original request into distinct outcomes and verify every one against the
collected responses. For example, "create a ticket and track TCK-123" requires
both a creation result and a tracking result for TCK-123. Creating a new ticket
does not satisfy a request to track an existing ticket. Do not return a generic
closing offer while any specific requested outcome remains incomplete.

IMPORTANT: when continuing or waiting, next_route must be one of:
faq, ticket, booking, it_support. When fully satisfied, next_route must be null.
If no supported capability remains, finish the response instead of selecting another agent.

Respond with a JSON object matching this schema:
{{"is_done": bool, "is_waiting_for_user": bool, "next_route": "<route or null>", "final_answer": "<text or null>"}}"""


class SupervisorDecision(BaseModel):
    is_done: bool
    is_waiting_for_user: bool = False
    next_route: Optional[Literal["faq", "ticket", "booking", "it_support"]] = None
    final_answer: Optional[str] = None

    @model_validator(mode="after")
    def validate_next_route(self):
        if (not self.is_done or self.is_waiting_for_user) and self.next_route is None:
            raise ValueError("Continuing or waiting requires a next_route")
        if self.is_waiting_for_user and not self.is_done:
            raise ValueError("Waiting requires is_done=true")
        return self


def supervisor_node(state: AgentState) -> dict:
    hop_count = state.get("hop_count", 0)
    messages = state["messages"]

    # Follow-up messages such as ticket details or "ok" must not replace the
    # request that may still contain work for another capability.
    original_query = state.get("active_request") or next(
        (m.content for m in reversed(messages) if isinstance(m, HumanMessage)), ""
    )
    last_ai = next(
        (m.content for m in reversed(messages) if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None)), ""
    )
    agent_responses = state.get("agent_responses", []) + [last_ai]
    request_start = next(
        (i for i in range(len(messages) - 1, -1, -1)
         if isinstance(messages[i], HumanMessage) and messages[i].content == original_query),
        0,
    )
    user_messages = "\n".join(
        f"- {m.content}" for m in messages[request_start:] if isinstance(m, HumanMessage)
    )
    # Preserve every user-facing agent result from this turn. The supervisor
    # decides control flow, but must not summarize away another agent's answer.
    turn_start = next(
        (i + 1 for i in range(len(messages) - 1, -1, -1)
         if isinstance(messages[i], HumanMessage)), 0,
    )
    turn_replies = [
        m.content for m in messages[turn_start:]
        if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None) and m.content
    ]
    turn_answer = "\n\n".join(dict.fromkeys(turn_replies))
    # The chat service exposes only the final plain AI reply of each turn.
    # Agent replies within the current turn are internal, not delivered replies.
    delivered_replies = []
    previous_reply = None
    for message in messages[request_start:]:
        if isinstance(message, HumanMessage):
            if previous_reply is not None:
                delivered_replies.append(previous_reply)
            previous_reply = None
        elif isinstance(message, AIMessage) and not getattr(message, "tool_calls", None):
            previous_reply = message.content

    current_route = state.get("route")
    if current_route not in VALID_ROUTES:
        current_route = state.get("last_completed_agent")

    def interrupted_response():
        answer = turn_answer
        answer += "\n\nI couldn't finish all parts of your request. Please ask me to continue."
        tasks = state.get("unfinished_tasks", [])
        if current_route in VALID_ROUTES:
            tasks = add_task(tasks, agent=current_route, question="Continue the unfinished request.")
        return {"route": "done", "hop_count": 0, "agent_responses": agent_responses,
                "unfinished_tasks": tasks, "messages": [AIMessage(content=answer.strip())]}

    if hop_count >= MAX_HOPS:
        agent_logger.warning(f"SUPERVISOR hop_count={hop_count} >= MAX_HOPS, forcing done")
        return interrupted_response()

    llm = get_chat_llm().with_structured_output(SupervisorDecision, method="json_mode")
    responses_text = "\n".join(f"- {r}" for r in state.get("agent_responses", []) if r)

    try:
        result: SupervisorDecision = llm.invoke(
            SUPERVISOR_PROMPT.format(original_query=original_query, agent_responses=responses_text,
                                     requested_routes=state.get("requested_routes", []),
                                     current_route=current_route,
                                     delivered_replies="\n\n".join(delivered_replies) or "None yet.",
                                     user_messages=user_messages, latest_result=last_ai,
                                     result_source=("confirmation execution or cancellation result"
                                                    if state.get("route") == "confirmed"
                                                    else "agent response"))
        )
    except Exception as e:
        agent_logger.warning("SUPERVISOR decision failed: %s", e)
        return interrupted_response()

    completed_routes = list(dict.fromkeys(state.get("completed_routes", [])))
    unvisited_routes = [
        route for route in state.get("requested_routes", [])
        if route in VALID_ROUTES and route != current_route and route not in completed_routes
    ]
    if result.is_done and result.is_waiting_for_user and result.next_route in unvisited_routes:
        # The current agent cannot ask on behalf of an agent that has not run.
        # Let that agent produce the actual clarification question first.
        if current_route in VALID_ROUTES and current_route not in completed_routes:
            completed_routes.append(current_route)
        agent_logger.info("SUPERVISOR visiting agent before waiting: %s", result.next_route)
        return {"route": result.next_route, "hop_count": hop_count + 1,
                "agent_responses": agent_responses, "completed_routes": completed_routes,
                "last_completed_agent": current_route}

    if result.is_done and result.is_waiting_for_user:
        agent_logger.info(f"SUPERVISOR hop={hop_count} -> WAITING_FOR_USER, adding task for agent={result.next_route!r}")
        tasks = add_task(
            state.get("unfinished_tasks", []),
            agent=result.next_route,
            question=last_ai,
        )
        return {"route": "done", "hop_count": 0, "agent_responses": agent_responses, "unfinished_tasks": tasks,
                "messages": [AIMessage(content=turn_answer or last_ai)]}

    if current_route in VALID_ROUTES and current_route not in completed_routes:
        completed_routes.append(current_route)
    unvisited_routes = [
        route for route in state.get("requested_routes", [])
        if route in VALID_ROUTES and route not in completed_routes
    ]
    if result.is_done and unvisited_routes:
        next_route = unvisited_routes[0]
        agent_logger.info("SUPERVISOR completing planned route before final answer: %s", next_route)
        return {"route": next_route, "hop_count": hop_count + 1,
                "agent_responses": agent_responses, "completed_routes": completed_routes,
                "last_completed_agent": current_route}

    if result.is_done:
        answer = turn_answer or last_ai
        agent_logger.info(f"SUPERVISOR hop={hop_count} -> DONE")
        return {"route": "done", "hop_count": 0, "agent_responses": [], "active_request": None,
                "requested_routes": [], "completed_routes": [], "last_completed_agent": None,
                "messages": [AIMessage(content=answer)]}

    agent_logger.info(f"SUPERVISOR hop={hop_count} -> continue to {result.next_route}")
    return {"route": result.next_route, "hop_count": hop_count + 1,
            "agent_responses": agent_responses, "completed_routes": completed_routes,
            "last_completed_agent": current_route}


def supervisor_decision(state: AgentState) -> str:
    mapping = {
        "faq": "rag_agent", "ticket": "ticket_agent", "booking": "booking_agent",
        "it_support": "it_support_agent", "done": "final",
    }
    return mapping.get(state["route"], "final")
