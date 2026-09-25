"""Booking-owned audit and outbox writes within a caller-owned transaction."""

import json
from typing import Any

from sqlalchemy.orm import Session

from booking_service.models import Booking, BookingAudit, BookingOutbox
from logger import request_id_context


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
            correlation_id=request_id_context.get(),
            causation_id=request_id_context.get(),
        )
    )
