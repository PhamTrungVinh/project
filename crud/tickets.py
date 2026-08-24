import uuid
from sqlalchemy.orm import Session

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
    return ticket


def get_ticket_by_code(db: Session, owner_id: int, ticket_code: str) -> Ticket:
    """Ownership check NGAY TRONG QUERY - owner_id luôn là điều kiện WHERE bắt buộc.
    Nếu ticket tồn tại nhưng thuộc user khác, hàm này trả về 'not found' giống hệt
    như khi ticket thực sự không tồn tại - không tiết lộ sự tồn tại của nó."""
    ticket = (
        db.query(Ticket)
        .filter(Ticket.ticket_code == ticket_code, Ticket.owner_id == owner_id)
        .first()
    )
    if ticket is None:
        raise NotFoundException(f"Ticket not found with code {ticket_code}")
    return ticket


def list_tickets(db: Session, owner_id: int, skip: int = 0, limit: int = 50) -> list[Ticket]:
    return (
        db.query(Ticket)
        .filter(Ticket.owner_id == owner_id)
        .order_by(Ticket.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def update_ticket(db: Session, owner_id: int, ticket_code: str, data: TicketUpdate) -> Ticket:
    ticket = get_ticket_by_code(db, owner_id, ticket_code)  # đã có ownership check

    if ticket.status in LOCKED_STATUSES:
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
    return ticket