from typing import Optional
from langchain_core.tools import tool

from database import get_db_session
from crud import bookings as booking_crud
from schemas.booking import BookingCreate, BookingUpdate
from utils.exceptions import NotFoundException, ConflictException
from services.memory_service import remember_episode
from logger import agent_logger


def build_booking_tools(owner_id: int, thread_id: str) -> list:
    @tool
    def book_room(
        reason: str,
        time: str,
        customer_name: Optional[str] = None,
        customer_phone: Optional[str] = None,
        note: Optional[str] = None,
        email: Optional[str] = None,
    ) -> str:
        """Book a meeting room. Required: reason, time (ABSOLUTE ISO datetime,
        e.g. '2026-08-25 14:00:00' - convert relative expressions like 'tomorrow'
        using the current date/time given in the system prompt before calling this).
        New bookings always start with status 'Scheduled'."""
        with get_db_session() as db:
            try:
                data = BookingCreate(
                    reason=reason, time=time, note=note,
                    customer_name=customer_name, customer_phone=customer_phone, email=email,
                )
            except Exception:
                return f"Could not parse time value: {time!r}. Please provide an absolute date/time."

            booking = booking_crud.create_booking(db, owner_id, data)
            remember_episode(db, owner_id, thread_id, f"Booked room: {reason}",
                              f"booking_code={booking.booking_code}, status=Scheduled")
        agent_logger.info(f"BOOKING_TOOL create booking_code={booking.booking_code} owner_id={owner_id}")
        return f"Booked room, booking_code: {booking.booking_code}, status: Scheduled."

    @tool
    def track_booking(booking_code: str) -> str:
        """Track a room booking by booking_code. Returns full booking info."""
        with get_db_session() as db:
            try:
                booking = booking_crud.get_booking_by_code(db, owner_id, booking_code)
            except NotFoundException:
                return f"Booking not found with code {booking_code}."
        return (
            f"booking_code: {booking.booking_code}\nreason: {booking.reason}\n"
            f"time: {booking.time}\nstatus: {booking.status.value}\n"
            f"customer_name: {booking.customer_name}\nnote: {booking.note}"
        )

    @tool
    def update_booking(
        booking_code: str,
        reason: Optional[str] = None,
        time: Optional[str] = None,
        customer_name: Optional[str] = None,
        customer_phone: Optional[str] = None,
        note: Optional[str] = None,
        email: Optional[str] = None,
    ) -> str:
        """Update an existing booking. Only provided fields are changed."""
        with get_db_session() as db:
            try:
                data = BookingUpdate(
                    reason=reason, time=time, note=note,
                    customer_name=customer_name, customer_phone=customer_phone, email=email,
                )
            except Exception:
                return f"Could not parse time value: {time!r}."

            try:
                booking_crud.update_booking(db, owner_id, booking_code, data)
            except NotFoundException:
                return f"Booking not found with code {booking_code}."
            except ConflictException as e:
                remember_episode(db, owner_id, thread_id, f"Tried to update booking {booking_code}", f"FAILED - {e.message}")
                return e.message
            remember_episode(db, owner_id, thread_id, f"Updated booking {booking_code}", "success")
        return f"Updated booking {booking_code}."

    @tool
    def cancel_booking(booking_code: str) -> str:
        """Cancel a room booking by booking_code."""
        with get_db_session() as db:
            try:
                booking_crud.cancel_booking(db, owner_id, booking_code)
            except NotFoundException:
                return f"Booking not found with code {booking_code}."
            except ConflictException as e:
                remember_episode(db, owner_id, thread_id, f"Tried to cancel booking {booking_code}", f"FAILED - {e.message}")
                return e.message
            remember_episode(db, owner_id, thread_id, f"Canceled booking {booking_code}", "success")
        return f"Canceled booking {booking_code}."

    return [book_room, track_booking, update_booking, cancel_booking]