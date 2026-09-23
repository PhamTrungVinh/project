"""Local transactional-outbox dispatcher for ticket domain events."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from models.ticket import TicketOutbox
from shared_platform.events import EventEnvelope

Publisher = Callable[[EventEnvelope], None]


@dataclass(frozen=True)
class DispatchResult:
    published: int
    failed: int


def _occurred_at(event: TicketOutbox):
    timestamp = event.occurred_at
    return timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)


def dispatch_pending(db: Session, publish: Publisher, *, limit: int = 100) -> DispatchResult:
    """Publish pending events and retain failed rows for a later retry.

    A real broker adapter can be supplied later; local tests pass a callable.
    The event is marked published only after the publisher returns successfully.
    """
    if not 1 <= limit <= 1_000:
        raise ValueError("limit must be between 1 and 1000")

    events = (
        db.query(TicketOutbox)
        .filter(TicketOutbox.published_at.is_(None))
        .order_by(TicketOutbox.occurred_at, TicketOutbox.id)
        .limit(limit)
        .all()
    )
    published = 0
    failed = 0
    for event in events:
        event.delivery_attempts += 1
        envelope = EventEnvelope(
            event_id=event.id,
            event_type=event.event_type,
            occurred_at=_occurred_at(event),
            producer="ticket-service",
            schema_version="v1",
            correlation_id="ticket-outbox",
            causation_id=None,
            payload=json.loads(event.payload_json),
        )
        try:
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
