import enum
import uuid

from sqlalchemy import Column, DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func

from database import Base


class TicketStatus(str, enum.Enum):
    PENDING = "Pending"
    RESOLVING = "Resolving"
    CANCELED = "Canceled"
    FINISHED = "Finished"


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, index=True)
    ticket_code = Column(String, unique=True, index=True)
    owner_id = Column(Integer, nullable=False, index=True)

    content = Column(String, nullable=False)
    description = Column(String, nullable=False)
    customer_name = Column(String, nullable=True)
    customer_phone = Column(String, nullable=True)
    email = Column(String, nullable=True)

    status = Column(
        SAEnum(TicketStatus, native_enum=False),
        default=TicketStatus.PENDING,
        nullable=False,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )


class TicketAudit(Base):
    """Append-only record of ticket commands performed by its owner."""

    __tablename__ = "ticket_audit"

    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False, index=True)
    owner_id = Column(Integer, nullable=False, index=True)
    action = Column(String(50), nullable=False)
    details_json = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TicketOutbox(Base):
    """Events committed atomically with ticket state; a worker publishes them later."""

    __tablename__ = "ticket_outbox"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    payload_json = Column(Text, nullable=False)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    delivery_attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    correlation_id = Column(String(128), nullable=True)
    causation_id = Column(String(128), nullable=True)
