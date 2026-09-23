"""Durable, owner-scoped state for sensitive chat actions."""

import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models.pending_action import PendingAction
from utils.exceptions import ConflictException, NotFoundException


def create(db: Session, owner_id: int, thread_id: str, agent: str, tool_call: dict, question: str, ttl_seconds: int) -> PendingAction:
    action = PendingAction(
        owner_id=owner_id, thread_id=thread_id, agent=agent, action_name=tool_call["name"],
        arguments_json=json.dumps(tool_call["args"]), question=question,
        idempotency_key=f"pending-action:{tool_call.get("id") or uuid.uuid4().hex}",
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
    )
    db.add(action)
    db.commit()
    db.refresh(action)
    return action


def decide(db: Session, owner_id: int, thread_id: str, action_id: str, approved: bool) -> PendingAction:
    action = db.query(PendingAction).filter_by(id=action_id, owner_id=owner_id, thread_id=thread_id).first()
    if action is None:
        raise NotFoundException("Pending action not found")
    now = datetime.now(timezone.utc)
    expires_at = action.expires_at if action.expires_at.tzinfo else action.expires_at.replace(tzinfo=timezone.utc)
    if action.status == "pending" and expires_at <= now:
        action.status = "expired"
        db.commit()
        raise ConflictException("This pending action has expired")
    desired = "approved" if approved else "rejected"
    if action.status in {"executed", desired}:
        return action
    if action.status != "pending":
        raise ConflictException(f"This pending action is already {action.status}")
    action.status = desired
    action.decided_at = now
    db.commit()
    db.refresh(action)
    return action


def mark_executed(db: Session, action: PendingAction) -> None:
    action.status = "executed"
    action.executed_at = datetime.now(timezone.utc)
    db.commit()


def active_tasks(db: Session, owner_id: int, thread_id: str) -> list[dict]:
    now = datetime.now(timezone.utc)
    actions = db.query(PendingAction).filter_by(owner_id=owner_id, thread_id=thread_id, status="pending").all()
    tasks = []
    for action in actions:
        expiry = action.expires_at if action.expires_at.tzinfo else action.expires_at.replace(tzinfo=timezone.utc)
        if expiry <= now:
            action.status = "expired"
            continue
        tasks.append({"id": action.id, "pending_action_id": action.id, "agent": action.agent, "question": action.question, "type": "confirmation", "tool_call": {"name": action.action_name, "args": json.loads(action.arguments_json)}})
    db.commit()
    return tasks
