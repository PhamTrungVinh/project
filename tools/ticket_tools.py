from typing import Annotated, Optional
from langchain.tools import tool
from langgraph.prebuilt import InjectedState

from state import AgentState
import db
from logger import db_logger
from memory import save_episode

VALID_STATUSES = ["Pending", "Resolving", "Canceled", "Finished"]
LOCKED_STATUSES = ("Finished", "Canceled")  # không được update nếu ticket đang ở trạng thái này


@tool
def create_ticket(
    content: str,
    description: str,
    state: Annotated[AgentState, InjectedState],
    customer_name: Optional[str] = None,
    customer_phone: Optional[str] = None,
    email: Optional[str] = None,
) -> str:
    """Create a new IT/customer support ticket.
    Required: content (ticket content), description (detailed description).
    Optional: customer_name, customer_phone, email.
    If email is not given, it is automatically injected from conversation context.
    New tickets always start with status 'Pending'.
    Returns the new ticket_id."""
    email = email or state.get("user_email")
    user_id = state.get("user_name", "unknown")
    thread_id = state.get("thread_id", "unknown")

    ticket_id = db.new_id("TCK")
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO tickets (ticket_id, content, description, customer_name, "
        "customer_phone, email, time, status, user_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (ticket_id, content, description, customer_name, customer_phone,
         email, db.now_iso(), "Pending", user_id),
    )
    conn.commit()
    conn.close()
    db_logger.info(f"CREATE ticket_id={ticket_id}")

    save_episode(
        user_id=user_id,
        conversation_id=thread_id,
        summary=f"User created ticket: {content}",
        outcome=f"ticket_id={ticket_id}, status=Pending",
    )

    return f"Created ticket {ticket_id}, status: Pending."


@tool
def track_ticket(
    ticket_id: str,
    state: Annotated[AgentState, InjectedState],
) -> str:
    """Track a support ticket by ticket_id.
    Returns full ticket info: content, description, status, customer_name,
    customer_phone, email, creation time.
    Only returns tickets that belong to the current user."""
    user_id = state.get("user_name", "unknown")

    conn = db.get_conn()
    row = conn.execute("SELECT * FROM tickets WHERE ticket_id=?", (ticket_id,)).fetchone()
    conn.close()

    if not row:
        return f"Ticket not found with ID {ticket_id}."

    d = dict(row)

    # Kiểm tra quyền sở hữu: chỉ cho xem ticket của chính user đó
    if d.get("user_id") != user_id:
        db_logger.warning(
            f"ACCESS_DENIED ticket_id={ticket_id} requested_by={user_id!r} "
            f"but belongs to={d.get('user_id')!r}"
        )
        return f"Ticket not found with ID {ticket_id}."  # trả về giống hệt "not found", không tiết lộ ticket có tồn tại

    return "\n".join(f"{k}: {v}" for k, v in d.items())


@tool
def update_ticket(
    ticket_id: str,
    state: Annotated[AgentState, InjectedState],
    content: Optional[str] = None,
    description: Optional[str] = None,
    customer_name: Optional[str] = None,
    customer_phone: Optional[str] = None,
    email: Optional[str] = None,
    status: Optional[str] = None,
) -> str:
    """Update an existing ticket. Only the fields provided are changed, others stay unchanged.
    Cannot update a ticket that is already 'Finished' or 'Canceled'.
    Valid status values: Pending, Resolving, Canceled, Finished.
    Email is auto-injected from context if not provided directly, but can be overridden."""

    user_id = state.get("user_name", "unknown")
    thread_id = state.get("thread_id", "unknown")

    conn = db.get_conn()
    row = conn.execute("SELECT * FROM tickets WHERE ticket_id=?", (ticket_id,)).fetchone()
    if not row:
        conn.close()
        return f"Ticket not found with ID {ticket_id}."

    current = dict(row)

    if current.get("user_id") != user_id:
        conn.close()
        db_logger.warning(f"ACCESS_DENIED update ticket_id={ticket_id} by={user_id!r}")
        return f"Ticket not found with ID {ticket_id}."

    if current["status"] in LOCKED_STATUSES:
        conn.close()
        save_episode(
            user_id=user_id,
            conversation_id=thread_id,
            summary=f"Tried to update ticket {ticket_id}",
            outcome=f"FAILED - ticket already {current['status']}",
        )
        return f"Cannot update ticket {ticket_id} because it is in the '{current['status']}' state."

    if status is not None and status not in VALID_STATUSES:
        conn.close()
        save_episode(
            user_id=user_id,
            conversation_id=thread_id,
            summary=f"Tried to update ticket {ticket_id} with invalid status",
            outcome=f"FAILED - invalid status value: {status}",
        )
        return f"Invalid status: {status}. Only {VALID_STATUSES} are allowed."

    email = email if email is not None else None  # user có thể override; nếu None và context có email thì auto-inject
    if email is None:
        context_email = state.get("user_email")
    else:
        context_email = email

    updates = {}
    for field, value in [
        ("content", content), ("description", description),
        ("customer_name", customer_name), ("customer_phone", customer_phone),
        ("email", email if email is not None else (context_email if context_email and current["email"] is None else None)),
        ("status", status),
    ]:
        if value is not None:
            updates[field] = value

    if not updates:
        conn.close()
        return "No fields provided for update."

    set_clause = ", ".join(f"{k}=?" for k in updates)
    conn.execute(f"UPDATE tickets SET {set_clause} WHERE ticket_id=?", (*updates.values(), ticket_id))
    conn.commit()
    conn.close()
    db_logger.info(f"UPDATE ticket_id={ticket_id} fields={list(updates.keys())}")

    save_episode(
        user_id=user_id,
        conversation_id=thread_id,
        summary=f"User updated ticket {ticket_id}, fields changed: {list(updates.keys())}",
        outcome="success",
    )

    return f"Updated ticket {ticket_id}: {', '.join(updates.keys())}."
