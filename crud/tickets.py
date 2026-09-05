import uuid
from sqlalchemy.orm import Session

from logger import db_logger
from models.ticket import Ticket, TicketStatus
from schemas.ticket import TicketCreate, TicketUpdate
from utils.exceptions import NotFoundException, ConflictException

LOCKED_STATUSES = (TicketStatus.FINISHED, TicketStatus.CANCELED)


def _generate_ticket_code() -> str:
    return f"TCK-{uuid.uuid4().hex[:8].upper()}"


def create_ticket(db: Session, owner_id: int, data: TicketCreate) -> Ticket:
    ticket = Ticket(
        ticket_code=_generate_ticket_code(),
        owner_id=owner_id,
        content=data.content,
        description=data.description,
        customer_name=data.customer_name,
        customer_phone=data.customer_phone,
        email=data.email,
        status=TicketStatus.PENDING,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    db_logger.info("ticket_created owner_id=%s ticket_code=%s status=%s", owner_id, ticket.ticket_code, ticket.status.value)
    return ticket


def get_ticket_by_code(db: Session, owner_id: int, ticket_code: str) -> Ticket:
    """Check ownership in the query itself: owner_id is always a required WHERE condition.
    A ticket owned by someone else returns the same not-found result as an absent ticket,
    preventing disclosure that it exists."""
    ticket = (
        db.query(Ticket)
        .filter(Ticket.ticket_code == ticket_code, Ticket.owner_id == owner_id)
        .first()
    )
    if ticket is None:
        db_logger.warning("ticket_not_found_or_not_owned owner_id=%s ticket_code=%s", owner_id, ticket_code)
        raise NotFoundException(f"Ticket not found with code {ticket_code}")
    db_logger.info("ticket_read owner_id=%s ticket_code=%s", owner_id, ticket_code)
    return ticket


def list_tickets(db: Session, owner_id: int, skip: int = 0, limit: int = 50) -> list[Ticket]:
    tickets = (
        db.query(Ticket)
        .filter(Ticket.owner_id == owner_id)
        .order_by(Ticket.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    db_logger.info("ticket_listed owner_id=%s count=%s", owner_id, len(tickets))
    return tickets


def update_ticket(db: Session, owner_id: int, ticket_code: str, data: TicketUpdate) -> Ticket:
    ticket = get_ticket_by_code(db, owner_id, ticket_code)  # ownership has already been checked

    if ticket.status in LOCKED_STATUSES:
        db_logger.warning("ticket_update_rejected_terminal_status owner_id=%s ticket_code=%s status=%s", owner_id, ticket_code, ticket.status.value)
        raise ConflictException(
            f"Cannot update ticket {ticket_code} because it is already '{ticket.status.value}'"
        )

    update_data = data.model_dump(exclude_unset=True, exclude_none=True)
    if not update_data:
        raise ConflictException("No fields provided for update")

    for field, value in update_data.items():
        setattr(ticket, field, value)

    db.commit()
    db.refresh(ticket)
    db_logger.info("ticket_updated owner_id=%s ticket_code=%s fields=%s", owner_id, ticket_code, sorted(update_data))
    return ticket


def update_ticket_status(db: Session, owner_id: int, ticket_code: str, status: TicketStatus) -> Ticket:
    ticket = get_ticket_by_code(db, owner_id, ticket_code)

    if ticket.status in LOCKED_STATUSES:
        db_logger.warning("ticket_status_update_rejected_terminal_status owner_id=%s ticket_code=%s status=%s", owner_id, ticket_code, ticket.status.value)
        raise ConflictException(
            f"Cannot change status of ticket {ticket_code} because it is already '{ticket.status.value}'"
        )

    previous_status = ticket.status.value
    ticket.status = status
    db.commit()
    db.refresh(ticket)
    db_logger.info("ticket_status_updated owner_id=%s ticket_code=%s from_status=%s to_status=%s", owner_id, ticket_code, previous_status, status.value)
    return ticket
