"""Booking-owned audit and outbox writes within a caller-owned transaction."""

import json
from typing import Any

from sqlalchemy.orm import Session

from models.booking import Booking, BookingAudit, BookingOutbox


def record_change(
    db: Session,
    *,
    booking: Booking,
    actor_id: int,
    event_type: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Persist audit history and an unpublished integration event atomically."""
    payload = {
        "booking_code": booking.booking_code,
        "owner_id": booking.owner_id,
        "time": booking.time.isoformat(),
        "status": booking.status.value,
    }
    if details:
        payload.update(details)
    db.add(
        BookingAudit(
            booking_id=booking.id,
            owner_id=actor_id,
            action=event_type,
            details_json=json.dumps(details or {}, sort_keys=True, default=str),
        )
    )
    db.add(
        BookingOutbox(
            booking_id=booking.id,
            event_type=event_type,
            payload_json=json.dumps(payload, sort_keys=True, default=str),
        )
    )
