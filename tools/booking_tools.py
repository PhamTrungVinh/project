from typing import Annotated, Optional
from langchain.tools import tool
from langgraph.prebuilt import InjectedState

from state import AgentState
import db
from logger import db_logger
from memory import save_episode

VALID_BOOKING_STATUSES = ["Scheduled", "Canceled", "Finished"]


@tool
def book_room(
    reason: str,
    time: str,
    state: Annotated[AgentState, InjectedState],
    customer_name: Optional[str] = None,
    customer_phone: Optional[str] = None,
    note: Optional[str] = None,
    email: Optional[str] = None,
) -> str:
    """Book a meeting room.
    Required: reason (reason for booking), time (booking time).
    Optional: customer_name, customer_phone, note, email.
    If email is not given, it is automatically injected from conversation context.
    New bookings always start with status 'Scheduled'.
    Returns the new booking_id."""
    email = email or state.get("user_email")
    user_id = state.get("user_name", "unknown")
    thread_id = state.get("thread_id", "unknown")

    booking_id = db.new_id("BKG")
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO bookings (booking_id, customer_name, customer_phone, email, "
        "reason, time, note, status, user_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (booking_id, customer_name, customer_phone, email, reason, time, note,
         "Scheduled", user_id),
    )
    conn.commit()
    conn.close()
    db_logger.info(f"Booked room booking_id={booking_id}, reason={reason}, time={time}")

    save_episode(
        user_id=user_id,
        conversation_id=thread_id,
        summary=f"User booked room: {booking_id} at {time}, reason: {reason}",
        outcome=f"booking_id={booking_id}, status=Scheduled",
    )

    return f"Booked, booking_id: {booking_id}, Status: Scheduled."


@tool
def track_booking(
    booking_id: str,
    state: Annotated[AgentState, InjectedState],
) -> str:
    """Track a room booking by booking_id. Returns full booking info."""
    user_id = state.get("user_name", "unknown")
    conn = db.get_conn()
    row = conn.execute("SELECT * FROM bookings WHERE booking_id=?", (booking_id,)).fetchone()
    conn.close()

    if not row:
        return f"Can't find booking with ID {booking_id}."

    d = dict(row)
    if d.get("user_id") != user_id:
        db_logger.warning(f"ACCESS_DENIED booking_id={booking_id} requested_by={user_id!r}")
        return f"Can't find booking with ID {booking_id}."
    
    return "\n".join(f"{k}: {v}" for k, v in d.items())


@tool
def update_booking(
    booking_id: str,
    state: Annotated[AgentState, InjectedState],
    reason: Optional[str] = None,
    time: Optional[str] = None,
    customer_name: Optional[str] = None,
    customer_phone: Optional[str] = None,
    note: Optional[str] = None,
    email: Optional[str] = None,
) -> str:
    """Update an existing room booking. Only provided fields are changed.
    Email is auto-injected from context if not provided directly, but can be overridden."""

    user_id = state.get("user_name", "unknown")
    thread_id = state.get("thread_id", "unknown")
    
    conn = db.get_conn()
    row = conn.execute("SELECT * FROM bookings WHERE booking_id=?", (booking_id,)).fetchone()
    if not row:
        conn.close()
        return f"Can't find booking with ID {booking_id}."

    current = dict(row)
    if current.get("user_id") != user_id:
        db_logger.warning(f"ACCESS_DENIED booking_id={booking_id} requested_by={user_id!r}")
        return f"Can't find booking with ID {booking_id}."
    
    if current["status"] == "Scheduled":
        conn.close()
        save_episode(
            user_id=user_id,
            conversation_id=thread_id,
            summary=f"Tried to update booking {booking_id}",
            outcome="FAILED - booking already Scheduled",
        )
        return f"Cannot update booking {booking_id} because it is already scheduled."

    resolved_email = email if email is not None else state.get("user_email")

    updates = {}
    for field, value in [
        ("reason", reason), ("time", time),
        ("customer_name", customer_name), ("customer_phone", customer_phone),
        ("note", note),
        ("email", email if email is not None else (resolved_email if current["email"] is None else None)),
    ]:
        if value is not None:
            updates[field] = value

    if not updates:
        conn.close()
        return "No fields provided for update."

    set_clause = ", ".join(f"{k}=?" for k in updates)
    conn.execute(f"UPDATE bookings SET {set_clause} WHERE booking_id=?", (*updates.values(), booking_id))
    conn.commit()
    conn.close()
    db_logger.info(f"Updated room booking_id={booking_id}, reason={reason}, time={time}")

    save_episode(
        user_id=user_id,
        conversation_id=thread_id,
        summary=f"User updated booking {booking_id}, fields changed: {list(updates.keys())}",
        outcome="success",
    )

    return f"Updated booking {booking_id}: {', '.join(updates.keys())}."


@tool
def cancel_booking(booking_id: str, state: Annotated[AgentState, InjectedState]) -> str:
    """Cancel a room booking by booking_id.
    Can only cancel bookings that are not already 'Scheduled'."""
    user_id = state.get("user_name", "unknown")
    thread_id = state.get("thread_id", "unknown")

    conn = db.get_conn()
    row = conn.execute("SELECT * FROM bookings WHERE booking_id=?", (booking_id,)).fetchone()
    if not row:
        conn.close()
        return f"Can't find booking with ID {booking_id}."

    current = dict(row)
    if current.get("user_id") != user_id:
        db_logger.warning(f"ACCESS_DENIED booking_id={booking_id} requested_by={user_id!r}")
        return f"Can't find booking with ID {booking_id}."
    
    if current["status"] == "Scheduled":
        conn.close()
        save_episode(
            user_id=user_id,
            conversation_id=thread_id,
            summary=f"Tried to cancel booking {booking_id}",
            outcome="FAILED - booking already Scheduled",
        )
        return f"Cannot cancel booking {booking_id} because it is already scheduled."

    conn.execute("UPDATE bookings SET status=? WHERE booking_id=?", ("Canceled", booking_id))
    conn.commit()
    conn.close()
    db_logger.info(f"Canceled room booking_id={booking_id}")

    save_episode(
        user_id=user_id,
        conversation_id=thread_id,
        summary=f"User canceled booking {booking_id}",
        outcome="success",
    )

    return f"Cancelled booking {booking_id}."