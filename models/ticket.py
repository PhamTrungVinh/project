import enum
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum as SAEnum
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
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

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