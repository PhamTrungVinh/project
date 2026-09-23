from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from config import BOOKING_ADAPTER
from database import get_db
from dependencies import get_current_user
from models.user import User
from schemas.booking import BookingCreate, BookingUpdate, BookingOut
from services import booking_service
from services.domain_remote_adapter import booking_request
from services.identity_service import claims_for_user

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("/", response_model=BookingOut)
def create_booking(
    data: BookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if BOOKING_ADAPTER == "http":
        return booking_request(
            current_user, "POST", "/bookings/",
            data.model_dump(mode="json", exclude_none=True),
            idempotency_key=idempotency_key,
        )
    return booking_service.create_booking(db, current_user.id, data, idempotency_key, claims_for_user(current_user))


@router.get("/", response_model=list[BookingOut])
def list_bookings(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if BOOKING_ADAPTER == "http":
        return booking_request(current_user, "GET", "/bookings/", query={"skip": skip, "limit": limit})
    return booking_service.list_bookings(db, current_user.id, skip=skip, limit=limit)


@router.get("/{booking_code}", response_model=BookingOut)
def get_booking(
    booking_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if BOOKING_ADAPTER == "http":
        return booking_request(current_user, "GET", f"/bookings/{booking_code}")
    return booking_service.get_booking(db, current_user.id, booking_code)


@router.patch("/{booking_code}", response_model=BookingOut)
def update_booking(
    booking_code: str,
    data: BookingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if BOOKING_ADAPTER == "http":
        return booking_request(
            current_user, "PATCH", f"/bookings/{booking_code}",
            data.model_dump(mode="json", exclude_none=True), idempotency_key=idempotency_key,
        )
    return booking_service.update_booking(db, current_user.id, booking_code, data, idempotency_key)


@router.post("/{booking_code}/cancel", response_model=BookingOut)
def cancel_booking(
    booking_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if BOOKING_ADAPTER == "http":
        return booking_request(
            current_user, "POST", f"/bookings/{booking_code}/cancel", {}, idempotency_key=idempotency_key,
        )
    return booking_service.cancel_booking(db, current_user.id, booking_code, idempotency_key)
