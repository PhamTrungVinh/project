from typing import Literal, Optional
from langchain.messages import HumanMessage
from pydantic import BaseModel

from config import llm
from state import AgentState
from logger import agent_logger
from tasks import prune_expired, remove_task


ROUTER_PROMPT = """You are the Primary Assistant.

Analyze the user's request and choose the single most appropriate agent from the following five categories:

- "faq": Questions about company policies, internal regulations, HR policies, or other information stored in the company's knowledge base.
- "ticket": Requests to create, track, update, or manage IT or customer support tickets.
- "it_support": Technical issues involving computers, software, hardware, networks, or other electronic devices that require troubleshooting.
- "booking": Requests to create, view, update, or cancel meeting room bookings.
- "web": general questions, news, calculations, requests to remember personal information/preferences (e.g., “remember that I prefer...”, “note that I work in...”), or anything unclear that falls outside the four categories above.

User request:
{query}

Respond with a JSON object matching this schema: {{"route": "<one of faq|ticket|it_support|booking|web>"}}
"""

VALID_ROUTES = {"faq", "ticket", "it_support", "booking", "web"}

class RouteDecision(BaseModel):
    route: Literal["faq", "ticket", "it_support", "booking", "web"]

router_llm = llm.with_structured_output(RouteDecision, method="json_mode")


class TaskMatch(BaseModel):
    matches_task_id: Optional[str] = None  # id của task đang chờ mà câu này trả lời, null nếu là câu hỏi mới


TASK_MATCH_PROMPT = """The system has these pending tasks waiting for more information from the user:

{tasks_list}

The user's new message:
{query}

Does this message provide the missing information for ONE of the pending tasks above?
If yes, respond with that task's id. If this is an unrelated new request instead,
respond with matches_task_id=null.

Respond with a JSON object: {{"matches_task_id": "<task_id or null>"}}"""

task_match_llm = llm.with_structured_output(TaskMatch, method="json_mode")


def router_node(state: AgentState) -> dict:
    query = state["messages"][-1].content
    tasks = prune_expired(state.get("unfinished_tasks", []))

    if tasks:
        agent_logger.info(f"ROUTER checking query={query!r} against {len(tasks)} pending task(s)")
        tasks_list = "\n".join(f'- id="{t["id"]}" (agent={t["agent"]}): {t["question"]}' for t in tasks)
        match: TaskMatch = task_match_llm.invoke(
            TASK_MATCH_PROMPT.format(tasks_list=tasks_list, query=query)
        )

        agent_logger.info(f"TASK_MATCH_RESULT matches_task_id={match.matches_task_id}")

        if match.matches_task_id:
            matched = next((t for t in tasks if t["id"] == match.matches_task_id), None)
            if matched:
                agent_logger.info(f"ROUTER matched pending task {matched['id']} -> route={matched['agent']}")
                return {
                    "route": matched["agent"],
                    "active_agent": matched["agent"],
                    "unfinished_tasks": remove_task(tasks, matched["id"]),  # task được giải quyết -> xóa khỏi hàng đợi
                }
            else:
                agent_logger.warning(
                    f"TASK_MATCH returned id={match.matches_task_id!r} but no such task found in current list"
                )

    # Không khớp task nào đang chờ (hoặc không có task nào) -> phân loại như bình thường
    result: RouteDecision = router_llm.invoke(ROUTER_PROMPT.format(query=query))
    agent_logger.info(f"ROUTER query={query!r} -> route={result.route}")
    return {"route": result.route, "active_agent": result.route, "unfinished_tasks": tasks}


def route_decision(state: AgentState) -> Literal[
    "rag_agent", "web_agent", "ticket_agent", "it_support_agent", "booking_agent"
]:
    mapping = {
        "faq": "rag_agent", "web": "web_agent", "ticket": "ticket_agent",
        "it_support": "it_support_agent", "booking": "booking_agent",
    }
    return mapping.get(state["route"], "web_agent")