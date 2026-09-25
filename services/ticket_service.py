"""Ticket capability interface for REST and chat adapters."""

from sqlalchemy.orm import Session

from crud import tickets as ticket_crud
from ticket_service.models import Ticket, TicketStatus
from schemas.ticket import TicketCreate, TicketUpdate, TicketOut
from shared_platform.auth_claims import AuthClaims
from services.idempotency_service import execute as execute_idempotent
from services import identity_service
from services.ticket_event_service import record_change
from utils.exceptions import ConflictException


ALLOWED_STATUS_TRANSITIONS = {
    TicketStatus.PENDING: {TicketStatus.RESOLVING, TicketStatus.CANCELED},
    TicketStatus.RESOLVING: {TicketStatus.FINISHED, TicketStatus.CANCELED},
    TicketStatus.CANCELED: set(),
    TicketStatus.FINISHED: set(),
}

def _with_trusted_contact(db: Session, owner_id: int, data: TicketCreate, claims: AuthClaims | None) -> TicketCreate:
    """Use account identity for customer name/email, never request/LLM values."""
    if claims is not None:
        return data.model_copy(update={"customer_name": claims.full_name, "email": claims.email})
    customer_name, email = identity_service.contact_for_owner(db, owner_id)
    return data.model_copy(update={"customer_name": customer_name, "email": email})



def _create_with_events(db: Session, owner_id: int, data: TicketCreate) -> Ticket:
    ticket = ticket_crud.create_ticket(db, owner_id, data, commit=False)
    record_change(db, ticket=ticket, actor_id=owner_id, event_type="TicketCreated")
    return ticket


def _update_with_events(db: Session, owner_id: int, ticket_code: str, data: TicketUpdate) -> Ticket:
    ticket = ticket_crud.update_ticket(db, owner_id, ticket_code, data, commit=False)
    record_change(
        db,
        ticket=ticket,
        actor_id=owner_id,
        event_type="TicketUpdated",
        details={"fields": sorted(data.model_dump(exclude_unset=True, exclude_none=True))},
    )
    return ticket


def _change_status_with_events(db: Session, owner_id: int, ticket_code: str, status: TicketStatus) -> Ticket:
    current = ticket_crud.get_ticket_by_code(db, owner_id, ticket_code)
    if status not in ALLOWED_STATUS_TRANSITIONS[current.status]:
        raise ConflictException(f"Invalid ticket status transition: {current.status.value} -> {status.value}")
    previous_status = current.status.value
    ticket = ticket_crud.update_ticket_status(db, owner_id, ticket_code, status, commit=False)
    record_change(
        db,
        ticket=ticket,
        actor_id=owner_id,
        event_type="TicketUpdated",
        previous_status=previous_status,
        details={"changed_field": "status"},
    )
    return ticket


def create_ticket(db: Session, owner_id: int, data: TicketCreate, idempotency_key: str | None = None, claims: AuthClaims | None = None) -> Ticket | dict:
    data = _with_trusted_contact(db, owner_id, data, claims)
    return execute_idempotent(db, owner_id, idempotency_key, "ticket.create", data.model_dump(mode="json"), lambda: _create_with_events(db, owner_id, data), lambda item: TicketOut.model_validate(item).model_dump(mode="json"))


def get_ticket(db: Session, owner_id: int, ticket_code: str) -> Ticket:
    return ticket_crud.get_ticket_by_code(db, owner_id, ticket_code)


def list_tickets(db: Session, owner_id: int, skip: int = 0, limit: int = 50) -> list[Ticket]:
    return ticket_crud.list_tickets(db, owner_id, skip=skip, limit=limit)


def update_ticket(db: Session, owner_id: int, ticket_code: str, data: TicketUpdate, idempotency_key: str | None = None) -> Ticket | dict:
    payload = {"ticket_code": ticket_code, **data.model_dump(mode="json", exclude_unset=True)}
    return execute_idempotent(db, owner_id, idempotency_key, "ticket.update", payload, lambda: _update_with_events(db, owner_id, ticket_code, data), lambda item: TicketOut.model_validate(item).model_dump(mode="json"))


def update_ticket_status(db: Session, owner_id: int, ticket_code: str, status: TicketStatus, idempotency_key: str | None = None) -> Ticket | dict:
    payload = {"ticket_code": ticket_code, "status": status.value}
    return execute_idempotent(db, owner_id, idempotency_key, "ticket.status", payload, lambda: _change_status_with_events(db, owner_id, ticket_code, status), lambda item: TicketOut.model_validate(item).model_dump(mode="json"))


def build_chat_tools(owner_id: int, thread_id: str, idempotency_key: str | None = None, claims: AuthClaims | None = None) -> list:
    """Return the LangChain adapter for this capability."""
    from tools.ticket_tools import build_ticket_tools

    return build_ticket_tools(owner_id, thread_id, idempotency_key, claims)
