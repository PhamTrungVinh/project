import json
from datetime import timezone

import pytest

from models.booking import BookingAudit, BookingOutbox
from schemas.booking import BookingCreate
from services import booking_service
from utils.exceptions import ConflictException


def test_booking_create_writes_audit_outbox_and_utc_time(db_session, test_user):
    booking = booking_service.create_booking(
        db_session,
        test_user.id,
        BookingCreate(reason="Project review", time="2026-09-20T09:00:00+07:00"),
        idempotency_key="booking-phase4-create",
    )

    audit = db_session.query(BookingAudit).one()
    outbox = db_session.query(BookingOutbox).one()
    # SQLite drops tzinfo, but the normalized persisted wall-clock value is UTC.
    assert booking.time.replace(tzinfo=timezone.utc).isoformat() == "2026-09-20T02:00:00+00:00"
    assert audit.booking_id == booking.id
    assert audit.action == "BookingCreated"
    assert outbox.event_type == "BookingCreated"
    assert json.loads(outbox.payload_json)["booking_code"] == booking.booking_code


def test_booking_availability_is_checked_before_commit(db_session, test_user, test_user_2):
    time = "2026-09-20T09:00:00+07:00"
    booking_service.create_booking(
        db_session, test_user.id, BookingCreate(reason="Project review", time=time)
    )

    with pytest.raises(ConflictException, match="no longer available"):
        booking_service.create_booking(
            db_session, test_user_2.id, BookingCreate(reason="Another meeting", time=time)
        )

    assert db_session.query(BookingAudit).count() == 1
    assert db_session.query(BookingOutbox).count() == 1


def test_booking_creation_uses_authenticated_contact(client, auth_headers, test_user):
    response = client.post(
        "/bookings/",
        json={
            "reason": "Project review",
            "time": "2026-09-20T09:00:00+07:00",
            "customer_name": "Spoofed Name",
            "email": "spoofed@example.com",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["customer_name"] == test_user.full_name
    assert response.json()["email"] == test_user.email
