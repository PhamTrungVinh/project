"""
Quản lý danh sách unfinished_tasks trong AgentState. Có 2 loại task:
- "info_request": agent hỏi thêm thông tin còn thiếu
- "confirmation": agent chờ user xác nhận trước khi thực thi 1 tool nhạy cảm
  (kèm sẵn tool_call = {"name": ..., "args": ...})
"""
import time
import uuid
from typing import Optional

from logger import agent_logger

MAX_UNFINISHED_TASKS = 5
DEFAULT_TTL_SECONDS = 600


def add_task(
    tasks: list[dict],
    agent: str,
    question: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
    task_type: str = "info_request",
    tool_call: Optional[dict] = None,
) -> list[dict]:
    new_task = {
        "id": uuid.uuid4().hex[:8],
        "agent": agent,
        "question": question,
        "created_at": time.time(),
        "ttl_seconds": ttl_seconds,
        "type": task_type,
        "tool_call": tool_call,
    }
    tasks = [new_task] + tasks

    agent_logger.info(
        f"TASK_ADD id={new_task['id']} agent={agent} type={task_type} ttl={ttl_seconds}s "
        f"question={question[:100]!r} total_tasks={len(tasks)}"
    )

    if len(tasks) > MAX_UNFINISHED_TASKS:
        dropped = tasks[MAX_UNFINISHED_TASKS:]
        tasks = tasks[:MAX_UNFINISHED_TASKS]
        for d in dropped:
            agent_logger.warning(f"TASK_DROPPED (exceeded MAX={MAX_UNFINISHED_TASKS}) id={d['id']} agent={d['agent']}")

    return tasks


def prune_expired(tasks: list[dict]) -> list[dict]:
    now = time.time()
    kept, expired = [], []
    for t in tasks:
        if now - t["created_at"] < t["ttl_seconds"]:
            kept.append(t)
        else:
            expired.append(t)

    for t in expired:
        agent_logger.info(f"TASK_EXPIRED id={t['id']} agent={t['agent']} age={now - t['created_at']:.0f}s")

    if kept:
        agent_logger.info(f"TASK_ACTIVE count={len(kept)} ids={[t['id'] for t in kept]}")

    return kept


def remove_task(tasks: list[dict], task_id: str) -> list[dict]:
    remaining = [t for t in tasks if t["id"] != task_id]
    agent_logger.info(f"TASK_RESOLVED id={task_id} remaining_count={len(remaining)}")
    return remaining