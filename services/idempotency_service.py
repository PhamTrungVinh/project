import hashlib
import json
from collections.abc import Callable
from typing import Any, TypeVar

from sqlalchemy.orm import Session

from models.idempotency import IdempotencyRecord
from utils.exceptions import ConflictException

T = TypeVar("T")


def execute(
    db: Session, owner_id: int, key: str | None, operation: str, payload: dict[str, Any],
    mutation: Callable[[], T], serialize: Callable[[T], dict[str, Any]],
) -> T | dict[str, Any]:
    """Execute once per owner/key, replaying the originally persisted response."""
    if not key:
        try:
            result = mutation()
            db.commit()
            return result
        except Exception:
            db.rollback()
            raise
    key = key.strip()
    if not key or len(key) > 255:
        raise ConflictException("Idempotency-Key must contain 1 to 255 characters")
    request_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    existing = db.query(IdempotencyRecord).filter_by(owner_id=owner_id, idempotency_key=key).first()
    if existing:
        if existing.operation != operation or existing.request_hash != request_hash:
            raise ConflictException("Idempotency-Key was already used for a different request")
        if existing.response_body is None:
            raise ConflictException("A request with this Idempotency-Key is still being processed")
        return json.loads(existing.response_body)
    record = IdempotencyRecord(owner_id=owner_id, idempotency_key=key, operation=operation, request_hash=request_hash)
    db.add(record)
    try:
        db.flush()
        result = mutation()
        response = serialize(result)
        record.response_body = json.dumps(response, default=str)
        record.status_code = 200
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
