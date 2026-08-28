from typing import Literal, Optional
from pydantic import BaseModel
from langchain_core.messages import AIMessage

from services.ai_adapter import get_chat_llm
from state import AgentState
from logger import agent_logger
from tasks import prune_expired, remove_task
from confirmation import execute_confirmed_tool_call

ROUTER_PROMPT = """You are the Primary Assistant.

Analyze the user's request and choose the single most appropriate agent from the following five categories:

- "faq": Questions about company policies, internal regulations, HR policies, or other information stored in the company's knowledge base.
- "ticket": Requests to create, track, update, or manage IT or customer support tickets.
- "it_support": Technical issues involving computers, software, hardware, networks, or other electronic devices that require troubleshooting.
- "booking": Requests to create, view, update, or cancel meeting room bookings.
- "web": general questions, news, calculations, requests to remember personal information/preferences (e.g., "remember that I prefer...", "note that I work in..."), or anything unclear that falls outside the four categories above.

User request:
{query}

Respond with a JSON object matching this schema: {{"route": "<one of faq|ticket|it_support|booking|web>"}}
"""


class RouteDecision(BaseModel):
    route: Literal["faq", "ticket", "it_support", "booking", "web"]


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
    tasks = prune_expired(state.get("unfinished_tasks", []))
    owner_id = int(state["user_name"])
    thread_id = state.get("thread_id", "unknown")

    if tasks:
        agent_logger.info(f"ROUTER checking query={query!r} against {len(tasks)} pending task(s)")
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
                    result_text = execute_confirmed_tool_call(
                        matched["agent"], owner_id, thread_id, matched["tool_call"]
                    )
                    return {"route": "confirmed", "unfinished_tasks": remaining,
                             "messages": [AIMessage(content=result_text)]}

                if match.intent == "cancel":
                    agent_logger.info(f"ROUTER confirmation CANCELED for task {matched['id']}")
                    return {"route": "confirmed", "unfinished_tasks": remaining,
                             "messages": [AIMessage(content="Ok, I won't proceed with that action.")]}

                agent_logger.info(f"ROUTER confirmation EDIT requested for task {matched['id']}, back to {matched['agent']}")
                return {"route": matched["agent"], "unfinished_tasks": remaining}
            else:
                agent_logger.info(f"ROUTER matched info_request task {matched['id']} -> route={matched['agent']}")
                return {"route": matched["agent"], "unfinished_tasks": remove_task(tasks, matched["id"])}

    route_llm = get_chat_llm().with_structured_output(RouteDecision, method="json_mode")
    result: RouteDecision = route_llm.invoke(ROUTER_PROMPT.format(query=query))
    agent_logger.info(f"ROUTER query={query!r} -> route={result.route} (fresh classification)")
    return {"route": result.route, "unfinished_tasks": tasks}


def route_decision(state: AgentState) -> Literal[
    "rag_agent", "web_agent", "ticket_agent", "it_support_agent", "booking_agent", "confirmed"
]:
    mapping = {
        "faq": "rag_agent", "web": "web_agent", "ticket": "ticket_agent",
        "it_support": "it_support_agent", "booking": "booking_agent",
        "confirmed": "confirmed",
    }
    return mapping.get(state["route"], "web_agent")