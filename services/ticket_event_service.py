"""Ticket-owned audit and outbox writes.

These helpers never commit: the caller commits the ticket, audit row, and
outbox event atomically through the idempotency transaction.
"""

import json
from typing import Any

from sqlalchemy.orm import Session

from models.ticket import Ticket, TicketAudit, TicketOutbox


def record_change(
    db: Session,
    *,
    ticket: Ticket,
    actor_id: int,
    event_type: str,
    previous_status: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Persist the ticket audit record and matching integration event."""
    payload = {
        "ticket_code": ticket.ticket_code,
        "owner_id": ticket.owner_id,
        "status": ticket.status.value,
    }
    if details:
        payload.update(details)
    audit_details = {"previous_status": previous_status, **(details or {})}
    db.add(
        TicketAudit(
            ticket_id=ticket.id,
            owner_id=actor_id,
            action=event_type,
            details_json=json.dumps(audit_details, sort_keys=True, default=str),
        )
    )
    db.add(
        TicketOutbox(
            ticket_id=ticket.id,
            event_type=event_type,
            payload_json=json.dumps(payload, sort_keys=True, default=str),
        )
    )
