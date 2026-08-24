"""
Quản lý danh sách unfinished_tasks: các task agent đang chờ user bổ sung
thông tin, có TTL, giới hạn số lượng tối đa.
"""
import time
import uuid
from logger import agent_logger

MAX_UNFINISHED_TASKS = 5
DEFAULT_TTL_SECONDS = 600  # 10 phút


def add_task(tasks: list[dict], agent: str, question: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> list[dict]:
    """Thêm 1 task mới vào đầu list. Nếu vượt MAX, bỏ task xa nhất (cũ nhất)."""
    new_task = {
        "id": uuid.uuid4().hex[:8],
        "agent": agent,
        "question": question,
        "created_at": time.time(),
        "ttl_seconds": ttl_seconds,
    }
    tasks = [new_task] + tasks
    agent_logger.info(
        f"TASK_ADD id={new_task['id']} agent={agent} ttl={ttl_seconds}s "
        f"question={question[:100]!r} total_tasks={len(tasks)}"
    )
    if len(tasks) > MAX_UNFINISHED_TASKS:
        dropped = tasks[MAX_UNFINISHED_TASKS:]
        tasks = tasks[:MAX_UNFINISHED_TASKS]
        for d in dropped:
            agent_logger.warning(f"TASK_DROPPED (exceeded MAX={MAX_UNFINISHED_TASKS}) id={d['id']} agent={d['agent']}") # bỏ task cũ nhất (cuối list)
    return tasks


def prune_expired(tasks: list[dict]) -> list[dict]:
    """Loại bỏ các task đã hết TTL."""
    now = time.time()
    kept, expired = [], []
    for t in tasks:
        age = now - t["created_at"]
        if age < t["ttl_seconds"]:
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