from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.sql import func
import enum
import uuid

from database import Base

class BookingStatus(str, enum.Enum):
    SCHEDULED = "Scheduled"
    CANCELED = "Canceled"
    FINISHED = "Finished"

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    booking_code = Column(String, unique=True, index=True)  # "BKG-xxxx" displayed to the user

    owner_id = Column(Integer, nullable=False, index=True)

    reason = Column(String, nullable=False)
    time = Column(DateTime(timezone=True), nullable=False)
    note = Column(String, nullable=True)
    customer_name = Column(String, nullable=True)
    customer_phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    status = Column(
        SAEnum(BookingStatus, native_enum=False),  # native_enum=False stores VARCHAR in SQLite for better compatibility
        default=BookingStatus.SCHEDULED,
        nullable=False,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )

class BookingAudit(Base):
    """Append-only record of booking commands performed by its owner."""

    __tablename__ = "booking_audit"

    id = Column(Integer, primary_key=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    owner_id = Column(Integer, nullable=False, index=True)
    action = Column(String(50), nullable=False)
    details_json = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BookingOutbox(Base):
    """Events committed atomically with booking state; a worker publishes later."""

    __tablename__ = "booking_outbox"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    payload_json = Column(String, nullable=False)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)
    delivery_attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(String, nullable=True)
    correlation_id = Column(String(128), nullable=True)
    causation_id = Column(String(128), nullable=True)
