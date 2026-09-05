import uuid
from sqlalchemy.orm import Session

from logger import db_logger
from models.booking import Booking, BookingStatus
from schemas.booking import BookingCreate, BookingUpdate
from utils.exceptions import NotFoundException, ConflictException


def _generate_booking_code() -> str:
    return f"BKG-{uuid.uuid4().hex[:8].upper()}"


def create_booking(db: Session, owner_id: int, data: BookingCreate) -> Booking:
    booking = Booking(booking_code=_generate_booking_code(), owner_id=owner_id, reason=data.reason,
                      time=data.time, note=data.note, customer_name=data.customer_name,
                      customer_phone=data.customer_phone, email=data.email, status=BookingStatus.SCHEDULED)
    db.add(booking)
    db.commit()
    db.refresh(booking)
    db_logger.info("booking_created owner_id=%s booking_code=%s status=%s", owner_id, booking.booking_code, booking.status.value)
    return booking


def get_booking_by_code(db: Session, owner_id: int, booking_code: str) -> Booking:
    booking = db.query(Booking).filter(Booking.booking_code == booking_code, Booking.owner_id == owner_id).first()
    if booking is None:
        db_logger.warning("booking_not_found_or_not_owned owner_id=%s booking_code=%s", owner_id, booking_code)
        raise NotFoundException(f"Booking not found with code {booking_code}")
    db_logger.info("booking_read owner_id=%s booking_code=%s", owner_id, booking_code)
    return booking


def list_bookings(db: Session, owner_id: int, skip: int = 0, limit: int = 50) -> list[Booking]:
    bookings = db.query(Booking).filter(Booking.owner_id == owner_id).order_by(Booking.created_at.desc()).offset(skip).limit(limit).all()
    db_logger.info("booking_listed owner_id=%s count=%s", owner_id, len(bookings))
    return bookings


def update_booking(db: Session, owner_id: int, booking_code: str, data: BookingUpdate) -> Booking:
    booking = get_booking_by_code(db, owner_id, booking_code)
    if booking.status == BookingStatus.FINISHED:
        db_logger.warning("booking_update_rejected_finished owner_id=%s booking_code=%s", owner_id, booking_code)
        raise ConflictException(f"Cannot update booking {booking_code} because it is already Finished")
    update_data = data.model_dump(exclude_unset=True, exclude_none=True)
    if not update_data:
        raise ConflictException("No fields provided for update")
    for field, value in update_data.items():
        setattr(booking, field, value)
    db.commit()
    db.refresh(booking)
    db_logger.info("booking_updated owner_id=%s booking_code=%s fields=%s", owner_id, booking_code, sorted(update_data))
    return booking


def cancel_booking(db: Session, owner_id: int, booking_code: str) -> Booking:
    booking = get_booking_by_code(db, owner_id, booking_code)
    if booking.status == BookingStatus.FINISHED:
        db_logger.warning("booking_cancel_rejected_finished owner_id=%s booking_code=%s", owner_id, booking_code)
        raise ConflictException(f"Cannot cancel booking {booking_code} because it is already Finished")
    booking.status = BookingStatus.CANCELED
    db.commit()
    db.refresh(booking)
    db_logger.info("booking_canceled owner_id=%s booking_code=%s", owner_id, booking_code)
    return booking
