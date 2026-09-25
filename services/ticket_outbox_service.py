"""Ticket-owned outbox dispatcher."""

from sqlalchemy.orm import Session

from ticket_service.models import TicketOutbox
from services.outbox_service import DispatchResult, Publisher, dispatch_pending as dispatch_domain_pending


def dispatch_pending(db: Session, publish: Publisher, *, limit: int = 100) -> DispatchResult:
    return dispatch_domain_pending(db, TicketOutbox, "ticket-service", publish, limit=limit)
