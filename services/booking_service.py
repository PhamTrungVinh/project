"""Booking capability interface for REST and chat adapters."""

from datetime import timezone
from sqlalchemy.orm import Session

from crud import bookings as booking_crud
from models.booking import Booking, BookingStatus
from schemas.booking import BookingCreate, BookingUpdate, BookingOut
from services.idempotency_service import execute as execute_idempotent

from shared_platform.auth_claims import AuthClaims
from services import identity_service
from services.booking_event_service import record_change
from services.date_service import DEFAULT_TIMEZONE
from utils.exceptions import ConflictException


def _normalize_time(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=DEFAULT_TIMEZONE)
    return value.astimezone(timezone.utc)


def _with_trusted_contact(db: Session, owner_id: int, data: BookingCreate, claims: AuthClaims | None) -> BookingCreate:
    customer_name, email = identity_service.contact_for_owner(db, owner_id)
    if claims is not None:
        return data.model_copy(update={"customer_name": claims.full_name, "email": claims.email})
    return data.model_copy(update={
        "time": _normalize_time(data.time),
        "customer_name": customer_name,
        "email": email,
    })


def _assert_available(db: Session, time, *, exclude_booking_code: str | None = None) -> None:
    query = db.query(Booking).filter(Booking.time == time, Booking.status == BookingStatus.SCHEDULED)
    if exclude_booking_code:
        query = query.filter(Booking.booking_code != exclude_booking_code)
    if query.first() is not None:
        raise ConflictException("The requested booking time is no longer available")


def _create_with_events(db: Session, owner_id: int, data: BookingCreate) -> Booking:
    _assert_available(db, data.time)
    booking = booking_crud.create_booking(db, owner_id, data, commit=False)
    record_change(db, booking=booking, actor_id=owner_id, event_type="BookingCreated")
    return booking


def _update_with_events(db: Session, owner_id: int, booking_code: str, data: BookingUpdate) -> Booking:
    update_data = data
    if data.time is not None:
        update_data = data.model_copy(update={"time": _normalize_time(data.time)})
        _assert_available(db, update_data.time, exclude_booking_code=booking_code)
    booking = booking_crud.update_booking(db, owner_id, booking_code, update_data, commit=False)
    record_change(db, booking=booking, actor_id=owner_id, event_type="BookingUpdated")
    return booking


def _cancel_with_events(db: Session, owner_id: int, booking_code: str) -> Booking:
    booking = booking_crud.cancel_booking(db, owner_id, booking_code, commit=False)
    record_change(
        db, booking=booking, actor_id=owner_id, event_type="BookingUpdated", details={"changed_field": "status"}
    )
    return booking
def create_booking(db: Session, owner_id: int, data: BookingCreate, idempotency_key: str | None = None, claims: AuthClaims | None = None) -> Booking | dict:
    data = _with_trusted_contact(db, owner_id, data, claims)
    return execute_idempotent(db, owner_id, idempotency_key, "booking.create", data.model_dump(mode="json"), lambda: _create_with_events(db, owner_id, data), lambda item: BookingOut.model_validate(item).model_dump(mode="json"))


def get_booking(db: Session, owner_id: int, booking_code: str) -> Booking:
    return booking_crud.get_booking_by_code(db, owner_id, booking_code)


def list_bookings(db: Session, owner_id: int, skip: int = 0, limit: int = 50) -> list[Booking]:
    return booking_crud.list_bookings(db, owner_id, skip=skip, limit=limit)


def update_booking(db: Session, owner_id: int, booking_code: str, data: BookingUpdate, idempotency_key: str | None = None) -> Booking | dict:
    payload = {"booking_code": booking_code, **data.model_dump(mode="json", exclude_unset=True)}
    return execute_idempotent(db, owner_id, idempotency_key, "booking.update", payload, lambda: _update_with_events(db, owner_id, booking_code, data), lambda item: BookingOut.model_validate(item).model_dump(mode="json"))


def cancel_booking(db: Session, owner_id: int, booking_code: str, idempotency_key: str | None = None) -> Booking | dict:
    return execute_idempotent(db, owner_id, idempotency_key, "booking.cancel", {"booking_code": booking_code}, lambda: _cancel_with_events(db, owner_id, booking_code), lambda item: BookingOut.model_validate(item).model_dump(mode="json"))


def build_chat_tools(owner_id: int, thread_id: str, idempotency_key: str | None = None, claims: AuthClaims | None = None) -> list:
    """Return the LangChain adapter for this capability."""
    from tools.booking_tools import build_booking_tools

    return build_booking_tools(owner_id, thread_id, idempotency_key, claims)
