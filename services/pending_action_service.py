"""Durable, owner-scoped state for sensitive chat actions."""

import json
import uuid
from threading import RLock
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.orm import Session

from chat_orchestrator.pending_action_model import PendingAction
from utils.exceptions import ConflictException, NotFoundException


_sqlite_decision_lock = RLock()


def create(db: Session, owner_id: int, thread_id: str, agent: str, tool_call: dict, question: str, ttl_seconds: int, request_context: dict | None = None) -> PendingAction:
    action = PendingAction(
        owner_id=owner_id, thread_id=thread_id, agent=agent, action_name=tool_call["name"],
        arguments_json=json.dumps(tool_call["args"]), question=question,
        idempotency_key=f"pending-action:{tool_call.get("id") or uuid.uuid4().hex}",
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds),
        request_context_json=json.dumps(request_context) if request_context else None,
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


def resolve(
    db: Session, owner_id: int, thread_id: str | None, action_id: str,
    approved: bool, execute: Callable[[PendingAction], str],
) -> PendingAction:
    """Resolve once and retain the result for repeat requests.

    PostgreSQL holds a row lock through execution. Local SQLite uses a process
    lock; remote tools receive the action's stable idempotency key for crash replay.
    """
    lock = _sqlite_decision_lock if db.bind.dialect.name == "sqlite" else None
    if lock:
        lock.acquire()
    try:
        query = db.query(PendingAction).filter_by(id=action_id, owner_id=owner_id)
        if thread_id is not None:
            query = query.filter_by(thread_id=thread_id)
        action = query.with_for_update().first()
        if action is None:
            raise NotFoundException("Pending action not found")
        desired = "executed" if approved else "rejected"
        if action.status == desired:
            return action
        if action.status == "pending":
            expiry = action.expires_at
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= datetime.now(timezone.utc):
                action.status = "expired"
                db.commit()
                raise ConflictException("This pending action has expired")
        if action.status == "approved" and approved:
            pass  # Recover a decision committed by the earlier chat flow.
        elif action.status != "pending":
            raise ConflictException(f"This pending action is already {action.status}")
        action.decided_at = datetime.now(timezone.utc)
        if approved:
            try:
                action.execution_result = str(execute(action))
            except Exception:
                db.rollback()
                raise
            action.status = "executed"
            action.executed_at = datetime.now(timezone.utc)
        else:
            action.status = "rejected"
        db.commit()
        db.refresh(action)
        return action
    finally:
        if lock:
            lock.release()


def pending_for_thread(db: Session, owner_id: int, thread_id: str) -> list[PendingAction]:
    now = datetime.now(timezone.utc)
    actions = db.query(PendingAction).filter_by(
        owner_id=owner_id, thread_id=thread_id, status="pending"
    ).all()
    pending = []
    for action in actions:
        expiry = action.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry <= now:
            action.status = "expired"
        else:
            pending.append(action)
    db.commit()
    return pending


def thread_for_action(db: Session, owner_id: int, action_id: str) -> str:
    action = db.query(PendingAction).filter_by(id=action_id, owner_id=owner_id).first()
    if action is None:
        raise NotFoundException("Pending action not found")
    return action.thread_id


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
