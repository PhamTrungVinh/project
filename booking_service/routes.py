"""Claim-authorized booking service API; it never reads identity tables."""

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_claims
from schemas.booking import BookingCreate, BookingOut, BookingUpdate
from services import booking_service
from shared_platform.auth_claims import AuthClaims

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("/", response_model=BookingOut)
def create_booking(data: BookingCreate, db: Session = Depends(get_db), claims: AuthClaims = Depends(get_current_claims), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    return booking_service.create_booking(db, claims.subject_id, data, idempotency_key, claims)


@router.get("/", response_model=list[BookingOut])
def list_bookings(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), claims: AuthClaims = Depends(get_current_claims)):
    return booking_service.list_bookings(db, claims.subject_id, skip, limit)


@router.get("/{booking_code}", response_model=BookingOut)
def get_booking(booking_code: str, db: Session = Depends(get_db), claims: AuthClaims = Depends(get_current_claims)):
    return booking_service.get_booking(db, claims.subject_id, booking_code)


@router.patch("/{booking_code}", response_model=BookingOut)
def update_booking(booking_code: str, data: BookingUpdate, db: Session = Depends(get_db), claims: AuthClaims = Depends(get_current_claims), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    return booking_service.update_booking(db, claims.subject_id, booking_code, data, idempotency_key)


@router.post("/{booking_code}/cancel", response_model=BookingOut)
def cancel_booking(booking_code: str, db: Session = Depends(get_db), claims: AuthClaims = Depends(get_current_claims), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    return booking_service.cancel_booking(db, claims.subject_id, booking_code, idempotency_key)
