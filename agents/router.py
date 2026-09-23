from typing import Literal, Optional
from pydantic import BaseModel
from langchain_core.messages import AIMessage

from services.ai_adapter import get_chat_llm
from state import AgentState
from logger import agent_logger
from tasks import prune_expired, remove_task
from confirmation import execute_confirmed_tool_call
from database import get_db_session
from services import pending_action_service
from utils.intent import is_standalone_pleasantry

ROUTER_PROMPT = """You are the Primary Assistant for a company support system.

Choose exactly one route for the user's CURRENT request. Use these strict precedence rules:

1. Choose "ticket" for any request to create, open, submit, track, check, update,
   change, resolve, cancel, or manage a support ticket. This rule takes priority
   whenever the user mentions a ticket, even if the request also contains a policy
   question or technical problem. Examples:
   - "I need to create a ticket" -> ticket
   - "Open a ticket for my VPN problem" -> ticket
   - "What is the status of ticket TCK-123?" -> ticket
   - "Change the description on my ticket" -> ticket

2. Choose "booking" for any request to create, view, track, update, reschedule,
   or cancel a meeting-room booking. Examples:
   - "Book a room tomorrow" -> booking
   - "Cancel my booking" -> booking

3. Choose "it_support" only when the user wants troubleshooting or technical help
   and is NOT asking to create or manage a ticket. Use it for standalone greetings,
   farewells, thanks, and acknowledgements allowed by the guardrail, so the LLM can
   respond naturally. Examples:
   - "My VPN will not connect" -> it_support
   - "Hello" -> it_support

4. Choose "faq" only for an informational question about company policy, HR policy,
   internal regulations, or the knowledge base. FAQ never creates, updates, tracks,
   or cancels a ticket or booking. Examples:
   - "What is the annual-leave policy?" -> faq
   - "How many days of parental leave do employees receive?" -> faq

Interpret the user's meaning, including paraphrases and informal language.
Identify ALL requested capabilities in requested_routes, without duplicates.
Choose route as the first capability to handle using the precedence above, and
include it in requested_routes. A technical problem mentioned as the subject of
a ticket is not a separate troubleshooting request unless the user asks for help
with it too. Do not infer an action from a general policy question.
Return only JSON matching this schema:
{{"route": "<faq|ticket|booking|it_support>", "requested_routes": ["<route>", "..."]}}

User request:
{query}
"""


class RouteDecision(BaseModel):
    route: Literal["faq", "ticket", "booking", "it_support"]
    requested_routes: list[Literal["faq", "ticket", "booking", "it_support"]]


class TaskMatch(BaseModel):
    matches_task_id: Optional[str] = None
    intent: Optional[Literal["confirm", "cancel", "edit"]] = None


TASK_MATCH_PROMPT = """The system has these pending tasks waiting for a response from the user:

{tasks_list}

The user's new message: {query}

For each task, note its type:
- "info_request": waiting for the user to provide missing information.
- "confirmation": waiting for the user to confirm/cancel/edit a pending action.

Decide if this message responds to ONE of the pending tasks above:
- If it responds to an "info_request" task, return matches_task_id (intent not needed).
- If it responds to a "confirmation" task, return matches_task_id AND intent:
  "confirm" (user agrees, e.g. "yes", "go ahead", "ok"), "cancel" (user declines,
  e.g. "no", "never mind", "cancel"), or "edit" (user wants to change something,
  e.g. "actually change the time to 3pm").
- If this is an unrelated NEW request instead, return matches_task_id=null.

Respond with a JSON object: {{"matches_task_id": "<id or null>", "intent": "<confirm|cancel|edit or null>"}}"""


def router_node(state: AgentState) -> dict:
    query = state["messages"][-1].content
    owner_id = int(state["user_name"])
    thread_id = state.get("thread_id", "unknown")
    checkpoint_tasks = prune_expired(state.get("unfinished_tasks", []))
    with get_db_session() as db:
        durable_tasks = pending_action_service.active_tasks(db, owner_id, thread_id)
    tasks = durable_tasks + [task for task in checkpoint_tasks if task.get("type") != "confirmation"]

    if tasks:
        agent_logger.info(
            "router_checking_pending_tasks count=%s",
            len(tasks),
            extra={"user_request": query},
        )
        tasks_list = "\n".join(
            f'- id="{t["id"]}" (agent={t["agent"]}, type={t["type"]}): {t["question"]}' for t in tasks
        )

        match_llm = get_chat_llm().with_structured_output(TaskMatch, method="json_mode")
        match: TaskMatch = match_llm.invoke(TASK_MATCH_PROMPT.format(tasks_list=tasks_list, query=query))
        agent_logger.info(f"TASK_MATCH_RESULT matches_task_id={match.matches_task_id} intent={match.intent}")

        if match.matches_task_id:
            matched = next((t for t in tasks if t["id"] == match.matches_task_id), None)

            if matched is None:
                agent_logger.warning(f"TASK_MATCH returned id={match.matches_task_id!r} but no such task found")
            elif matched["type"] == "confirmation":
                remaining = remove_task(tasks, matched["id"])

                if match.intent == "confirm":
                    agent_logger.info(f"ROUTER confirmation CONFIRMED for task {matched['id']}, executing tool directly")
                    pending_action_id = matched.get("pending_action_id")
                    if pending_action_id:
                        with get_db_session() as db:
                            action = pending_action_service.decide(db, owner_id, thread_id, pending_action_id, approved=True)
                            result_text = execute_confirmed_tool_call(
                                matched["agent"], owner_id, thread_id, matched["tool_call"], action.idempotency_key
                            )
                            pending_action_service.mark_executed(db, action)
                    else:
                        result_text = execute_confirmed_tool_call(
                            matched["agent"], owner_id, thread_id, matched["tool_call"]
                        )
                    agent_logger.info(
                        "router_selected_route",
                        extra={"user_request": query, "route": "confirmed"},
                    )
                    return {"route": "confirmed", "unfinished_tasks": remaining, "simple_pleasantry": False,
                             "last_completed_agent": matched["agent"],
                             "messages": [AIMessage(content=result_text)]}

                if match.intent == "cancel":
                    pending_action_id = matched.get("pending_action_id")
                    if pending_action_id:
                        with get_db_session() as db:
                            pending_action_service.decide(db, owner_id, thread_id, pending_action_id, approved=False)
                    agent_logger.info(f"ROUTER confirmation CANCELED for task {matched['id']}")
                    agent_logger.info(
                        "router_selected_route",
                        extra={"user_request": query, "route": "confirmed"},
                    )
                    return {"route": "confirmed", "unfinished_tasks": remaining, "simple_pleasantry": False,
                             "last_completed_agent": matched["agent"],
                             "messages": [AIMessage(content="Ok, I won't proceed with that action.")]}

                agent_logger.info(f"ROUTER confirmation EDIT requested for task {matched['id']}, back to {matched['agent']}")
                agent_logger.info(
                    "router_selected_route",
                    extra={"user_request": query, "route": matched["agent"]},
                )
                return {"route": matched["agent"], "unfinished_tasks": remaining, "simple_pleasantry": False}
            else:
                agent_logger.info(f"ROUTER matched info_request task {matched['id']} -> route={matched['agent']}")
                agent_logger.info(
                    "router_selected_route",
                    extra={"user_request": query, "route": matched["agent"]},
                )
                return {"route": matched["agent"], "unfinished_tasks": remove_task(tasks, matched["id"]), "simple_pleasantry": False}

    if is_standalone_pleasantry(query):
        agent_logger.info(
            "router_selected_route",
            extra={"user_request": query, "route": "it_support"},
        )
        return {"route": "it_support", "unfinished_tasks": tasks, "simple_pleasantry": True,
                "active_request": query, "requested_routes": ["it_support"],
                "completed_routes": [], "last_completed_agent": None}

    route_llm = get_chat_llm().with_structured_output(RouteDecision, method="json_mode")
    result: RouteDecision = route_llm.invoke(ROUTER_PROMPT.format(query=query))
    agent_logger.info(
        "router_selected_route",
        extra={"user_request": query, "route": result.route},
    )
    return {"route": result.route, "unfinished_tasks": tasks, "simple_pleasantry": False,
            "active_request": query,
            "requested_routes": list(dict.fromkeys([result.route, *result.requested_routes])),
            "completed_routes": [], "last_completed_agent": None,
            "agent_responses": [], "hop_count": 0}


def route_decision(state: AgentState) -> Literal[
    "rag_agent", "ticket_agent", "booking_agent", "it_support_agent", "confirmed"
]:
    mapping = {
        "faq": "rag_agent", "ticket": "ticket_agent", "booking": "booking_agent",
        "it_support": "it_support_agent", "confirmed": "confirmed",
    }
    return mapping.get(state["route"], "it_support_agent")
