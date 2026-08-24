"""
CRUD cho Booking. Cùng nguyên tắc với crud/tickets.py: owner_id luôn nằm
trong WHERE clause của mọi query đọc/sửa/xóa.
"""
import uuid
from sqlalchemy.orm import Session

from models.booking import Booking, BookingStatus
from schemas.booking import BookingCreate, BookingUpdate
from utils.exceptions import NotFoundException, ConflictException


def _generate_booking_code() -> str:
    return f"BKG-{uuid.uuid4().hex[:8].upper()}"


def create_booking(db: Session, owner_id: int, data: BookingCreate) -> Booking:
    booking = Booking(
        booking_code=_generate_booking_code(),
        owner_id=owner_id,
        reason=data.reason,
        time=data.time,
        note=data.note,
        customer_name=data.customer_name,
        customer_phone=data.customer_phone,
        email=data.email,
        status=BookingStatus.SCHEDULED,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


def get_booking_by_code(db: Session, owner_id: int, booking_code: str) -> Booking:
    booking = (
        db.query(Booking)
        .filter(Booking.booking_code == booking_code, Booking.owner_id == owner_id)
        .first()
    )
    if booking is None:
        raise NotFoundException(f"Booking not found with code {booking_code}")
    return booking


def list_bookings(db: Session, owner_id: int, skip: int = 0, limit: int = 50) -> list[Booking]:
    return (
        db.query(Booking)
        .filter(Booking.owner_id == owner_id)
        .order_by(Booking.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def update_booking(db: Session, owner_id: int, booking_code: str, data: BookingUpdate) -> Booking:
    booking = get_booking_by_code(db, owner_id, booking_code)

    if booking.status == BookingStatus.FINISHED:
        raise ConflictException(f"Cannot update booking {booking_code} because it is already Finished")

    update_data = data.model_dump(exclude_unset=True, exclude_none=True)
    if not update_data:
        raise ConflictException("No fields provided for update")

    for field, value in update_data.items():
        setattr(booking, field, value)

    db.commit()
    db.refresh(booking)
    return booking


def cancel_booking(db: Session, owner_id: int, booking_code: str) -> Booking:
    booking = get_booking_by_code(db, owner_id, booking_code)

    if booking.status == BookingStatus.FINISHED:
        raise ConflictException(f"Cannot cancel booking {booking_code} because it is already Finished")

    booking.status = BookingStatus.CANCELED
    db.commit()
    db.refresh(booking)
    return booking