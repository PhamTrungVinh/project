from unittest.mock import patch
from sqlalchemy.orm import Session
from models.user import User
from tools.ticket_tools import build_ticket_tools
from tools.booking_tools import build_booking_tools


def test_ticket_tools_lifecycle(db_session: Session, test_user: User):
    with patch("services.memory_service.remember_episode"):
        tools = build_ticket_tools(owner_id=test_user.id, thread_id="thread-test-1")
        create_t, track_t, update_t, update_status_t = tools

        # 1. Create ticket
        create_res = create_t.invoke({
            "content": "Cannot access printer",
            "description": "Printer on 3rd floor shows error",
            "customer_name": "Test User",
            "customer_phone": "0123456789",
            "email": test_user.email,
        })
        assert "Created ticket TCK-" in create_res
        ticket_code = create_res.split("Created ticket ")[1].split(",")[0].strip()

        # 2. Track ticket
        track_res = track_t.invoke({"ticket_code": ticket_code})
        assert ticket_code in track_res
        assert "Cannot access printer" in track_res
        assert "Pending" in track_res

        # 3. Update ticket
        update_res = update_t.invoke({
            "ticket_code": ticket_code,
            "description": "Printer on 4th floor instead",
        })
        assert "Updated ticket" in update_res

        # 4. Update status
        status_res = update_status_t.invoke({
            "ticket_code": ticket_code,
            "status": "Resolving",
        })
        assert "status changed to Resolving" in status_res

        # 5. Invalid status test
        invalid_status_res = update_status_t.invoke({
            "ticket_code": ticket_code,
            "status": "InvalidStatus",
        })
        assert "Invalid status" in invalid_status_res


def test_booking_tools_lifecycle(db_session: Session, test_user: User):
    with patch("services.memory_service.remember_episode"):
        tools = build_booking_tools(owner_id=test_user.id, thread_id="thread-test-2")
        book_r, track_r, update_r, cancel_r = tools

        # 1. Book room
        book_res = book_r.invoke({
            "reason": "Team standup",
            "time": "2026-09-12 10:00:00",
            "customer_name": "Test User",
            "customer_phone": "0123456789",
            "note": "Need whiteboard",
            "email": test_user.email,
        })
        assert "Booked room, booking_code: BKG-" in book_res
        booking_code = book_res.split("booking_code: ")[1].split(",")[0].strip()

        # 2. Track booking
        track_res = track_r.invoke({"booking_code": booking_code})
        assert booking_code in track_res
        assert "Team standup" in track_res
        assert "Scheduled" in track_res

        # 3. Update booking
        update_res = update_r.invoke({
            "booking_code": booking_code,
            "note": "Need whiteboard and markers",
        })
        assert f"Updated booking {booking_code}" in update_res

        # 4. Cancel booking
        cancel_res = cancel_r.invoke({"booking_code": booking_code})
        assert f"Canceled booking {booking_code}" in cancel_res
