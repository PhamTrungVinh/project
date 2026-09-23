from typing import Optional
from langchain_core.tools import tool
from fastapi import HTTPException
from config import BOOKING_ADAPTER, BOOKING_SERVICE_URL

from database import get_db_session
from services import booking_service, identity_service
from schemas.booking import BookingCreate, BookingUpdate
from utils.exceptions import NotFoundException, ConflictException
from services.memory_service import remember_episode
from logger import agent_logger
from services.date_service import format_local_datetime
from services.domain_remote_adapter import domain_request_for_claims


def build_booking_tools(owner_id: int, thread_id: str, idempotency_key: str | None = None, claims=None) -> list:
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
                profile_name, profile_email = identity_service.contact_for_owner(db, owner_id)
                data = BookingCreate(
                    reason=reason,
                    time=time,
                    # Account identity is authoritative; tool-call arguments come from the LLM.
                    customer_name=profile_name or customer_name,
                    customer_phone=customer_phone,
                    note=note,
                    email=profile_email or email,
                )
            except Exception:
                return f"Could not parse time value: {time!r}."

            if BOOKING_ADAPTER == "http" and claims is not None:
                booking = domain_request_for_claims(
                    BOOKING_SERVICE_URL, claims, "POST", "/bookings/",
                    data.model_dump(mode="json", exclude_none=True), idempotency_key=idempotency_key,
                )
                booking_code = booking["booking_code"]
            else:
                booking = booking_service.create_booking(db, owner_id, data, idempotency_key, claims)
                booking_code = booking.booking_code

            try:
                remember_episode(db, owner_id, thread_id, f"Booked room: {reason}",
                                f"booking_code={booking_code}, status=Scheduled")
            except Exception as ex:
                agent_logger.warning(f"remember_episode failed after booking created: {ex}")

        agent_logger.info(f"BOOKING_TOOL create booking_code={booking_code} owner_id={owner_id}")
        return f"Booked room, booking_code: {booking_code}, status: Scheduled."

    @tool
    def track_booking(booking_code: str) -> str:
        """Track a room booking by booking_code. Returns full booking info."""
        with get_db_session() as db:
            try:
                if BOOKING_ADAPTER == "http" and claims is not None:
                    booking = domain_request_for_claims(BOOKING_SERVICE_URL, claims, "GET", f"/bookings/{booking_code}")
                else:
                    booking = booking_service.get_booking(db, owner_id, booking_code)
            except (NotFoundException, HTTPException):
                return f"Booking not found with code {booking_code}."
        if isinstance(booking, dict):
            return (
                f"booking_code: {booking['booking_code']}\nreason: {booking['reason']}\n"
                f"time: {booking['time']}\nstatus: {booking['status']}\n"
                f"customer_name: {booking.get('customer_name')}\ncustomer_phone: {booking.get('customer_phone')}\n"
                f"email: {booking.get('email')}\nnote: {booking.get('note')}"
            )
        return (
            f"booking_code: {booking.booking_code}\nreason: {booking.reason}\n"
            f"time: {format_local_datetime(booking.time)}\nstatus: {booking.status.value}\n"
            f"customer_name: {booking.customer_name}\ncustomer_phone: {booking.customer_phone}\n"
            f"email: {booking.email}\nnote: {booking.note}"

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
                if BOOKING_ADAPTER == "http" and claims is not None:
                    domain_request_for_claims(
                        BOOKING_SERVICE_URL, claims, "PATCH", f"/bookings/{booking_code}",
                        data.model_dump(mode="json", exclude_none=True), idempotency_key=idempotency_key,
                    )
                else:
                    booking_service.update_booking(db, owner_id, booking_code, data, idempotency_key)
            except NotFoundException:
                return f"Booking not found with code {booking_code}."
            except ConflictException as e:
                remember_episode(db, owner_id, thread_id, f"Tried to update booking {booking_code}", f"FAILED - {e.message}")
                return e.message
            except HTTPException as e:
                return str(e.detail)
            remember_episode(db, owner_id, thread_id, f"Updated booking {booking_code}", "success")
        return f"Updated booking {booking_code}."

    @tool
    def cancel_booking(booking_code: str) -> str:
        """Cancel a room booking by booking_code."""
        with get_db_session() as db:
            try:
                if BOOKING_ADAPTER == "http" and claims is not None:
                    domain_request_for_claims(
                        BOOKING_SERVICE_URL, claims, "POST", f"/bookings/{booking_code}/cancel", {},
                        idempotency_key=idempotency_key,
                    )
                else:
                    booking_service.cancel_booking(db, owner_id, booking_code, idempotency_key)
            except NotFoundException:
                return f"Booking not found with code {booking_code}."
            except ConflictException as e:
                remember_episode(db, owner_id, thread_id, f"Tried to cancel booking {booking_code}", f"FAILED - {e.message}")
                return e.message
            except HTTPException as e:
                return str(e.detail)
            remember_episode(db, owner_id, thread_id, f"Canceled booking {booking_code}", "success")
        return f"Canceled booking {booking_code}."

    return [book_room, track_booking, update_booking, cancel_booking]