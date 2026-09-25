"""Publish committed domain events with retry-safe outbox bookkeeping."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from shared_platform.events import ALLOWED_PAYLOAD_FIELDS, EventEnvelope


Publisher = Callable[[EventEnvelope], None]


@dataclass(frozen=True)
class DispatchResult:
    published: int
    failed: int


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def dispatch_pending(db: Session, model, producer: str, publish: Publisher, *, limit: int = 100) -> DispatchResult:
    if not 1 <= limit <= 1_000:
        raise ValueError("limit must be between 1 and 1000")
    query = (
        db.query(model)
        .filter(model.published_at.is_(None))
        .order_by(model.occurred_at, model.id)
        .limit(limit)
    )
    if db.bind.dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    events = query.all()
    published = failed = 0
    for event in events:
        event.delivery_attempts += 1
        try:
            payload = json.loads(event.payload_json)
            payload = {key: value for key, value in payload.items()
                       if key in ALLOWED_PAYLOAD_FIELDS[producer]}
            envelope = EventEnvelope(
                event_id=event.id,
                event_type=event.event_type,
                occurred_at=_aware(event.occurred_at),
                producer=producer,
                schema_version="v1",
                correlation_id=event.correlation_id or f"legacy:{event.id}",
                causation_id=event.causation_id,
                payload=payload,
            )
            publish(envelope)
        except Exception as exc:
            event.last_error = str(exc)[:2_000]
            failed += 1
        else:
            event.published_at = datetime.now(timezone.utc)
            event.last_error = None
            published += 1
    db.commit()
    return DispatchResult(published=published, failed=failed)


def outbox_stats(db: Session, model) -> dict:
    pending = db.query(model).filter(model.published_at.is_(None)).all()
    oldest = min((_aware(item.occurred_at) for item in pending), default=None)
    return {
        "pending": len(pending),
        "failed": sum(item.last_error is not None for item in pending),
        "oldest_age_seconds": max(0, int((datetime.now(timezone.utc) - oldest).total_seconds())) if oldest else 0,
    }
