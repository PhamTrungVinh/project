from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models.user import User
from schemas.booking import BookingCreate, BookingUpdate, BookingOut
from crud import bookings as booking_crud

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post("/", response_model=BookingOut)
def create_booking(
    data: BookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return booking_crud.create_booking(db, current_user.id, data)


@router.get("/", response_model=list[BookingOut])
def list_bookings(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return booking_crud.list_bookings(db, current_user.id, skip=skip, limit=limit)


@router.get("/{booking_code}", response_model=BookingOut)
def get_booking(
    booking_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return booking_crud.get_booking_by_code(db, current_user.id, booking_code)


@router.patch("/{booking_code}", response_model=BookingOut)
def update_booking(
    booking_code: str,
    data: BookingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return booking_crud.update_booking(db, current_user.id, booking_code, data)


@router.post("/{booking_code}/cancel", response_model=BookingOut)
def cancel_booking(
    booking_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return booking_crud.cancel_booking(db, current_user.id, booking_code)