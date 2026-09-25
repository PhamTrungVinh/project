from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker

from event_service.app import create_app
from scripts.migrate_service import migrate
from scripts.run_outbox_worker import run_once
from logger import request_id_context
from models.booking import BookingOutbox
from models.ticket import TicketOutbox
from schemas.booking import BookingCreate
from schemas.ticket import TicketCreate
from services import booking_service, ticket_service
from services.booking_outbox_service import dispatch_pending as dispatch_bookings
from services.outbox_service import outbox_stats
from services.ticket_outbox_service import dispatch_pending as dispatch_tickets
from shared_platform.events import EventEnvelope


def _event():
    return EventEnvelope(
        event_id="123e4567-e89b-12d3-a456-426614174000",
        event_type="TicketCreated",
        occurred_at=datetime.now(timezone.utc),
        producer="ticket-service",
        schema_version="v1",
        correlation_id="request-123",
        causation_id="request-123",
        payload={"ticket_code": "TCK-1", "status": "Pending"},
    )


def test_event_inbox_deduplicates_and_rejects_conflicts(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENT_SERVICE_TOKEN", "local-test-token")
    database_url = f"sqlite:///{tmp_path / 'events.db'}"
    migrate("event", database_url)
    app = create_app(database_url)
    event = _event().model_dump(mode="json")
    headers = {"X-Internal-Service-Token": "local-test-token"}
    with TestClient(app) as client:
        assert client.post("/v1/events", json=event).status_code == 401
        accepted = client.post("/v1/events", json=event, headers=headers)
        duplicate = client.post("/v1/events", json=event, headers=headers)
        conflict = client.post(
            "/v1/events", json={**event, "payload": {"ticket_code": "TCK-2", "status": "Pending"}}, headers=headers,
        )
        stored = client.get(f"/v1/events/{event['event_id']}", headers=headers)
        metrics = client.get("/metrics")
    assert accepted.json()["status"] == "accepted"
    assert duplicate.json()["status"] == "duplicate"
    assert conflict.status_code == 409
    assert stored.json() == event
    assert metrics.json()["events_received_total"] == 1
    with TestClient(create_app(database_url)) as restarted:
        assert restarted.post("/v1/events", json=event, headers=headers).json()["status"] == "duplicate"
        assert restarted.get("/metrics").json()["events_received_total"] == 1


def test_event_envelope_rejects_sensitive_or_unknown_payload():
    data = _event().model_dump()
    data["payload"] = {"ticket_code": "TCK-1", "email": "private@example.com"}
    with pytest.raises(ValidationError):
        EventEnvelope(**data)
    data["payload"] = {"ticket_code": "TCK-1"}
    with pytest.raises(ValidationError):
        EventEnvelope(**data)
    data["payload"] = {"ticket_code": "TCK-1", "status": "Pending"}
    data["schema_version"] = "v2"
    with pytest.raises(ValidationError):
        EventEnvelope(**data)


def test_ticket_and_booking_outboxes_retry_and_publish_durable_events(
    db_session, test_user, tmp_path, monkeypatch,
):
    monkeypatch.setenv("EVENT_SERVICE_TOKEN", "local-test-token")
    database_url = f"sqlite:///{tmp_path / 'events.db'}"
    migrate("event", database_url)
    app = create_app(database_url)
    token = request_id_context.set("chat-turn-42")
    try:
        ticket_service.create_ticket(
            db_session, test_user.id,
            TicketCreate(content="VPN", description="Cannot connect"),
        )
        booking_service.create_booking(
            db_session, test_user.id,
            BookingCreate(reason="Review", time="2030-01-01T09:00:00+07:00"),
        )
    finally:
        request_id_context.reset(token)
    ticket = db_session.query(TicketOutbox).one()
    booking = db_session.query(BookingOutbox).one()
    assert ticket.correlation_id == booking.correlation_id == "chat-turn-42"

    with TestClient(app) as client:
        def publish(event):
            response = client.post(
                "/v1/events", json=event.model_dump(mode="json"),
                headers={"X-Internal-Service-Token": "local-test-token"},
            )
            response.raise_for_status()

        def fail(_event):
            raise RuntimeError("receiver offline")

        failed = dispatch_bookings(db_session, fail)
        assert failed.failed == 1
        assert outbox_stats(db_session, BookingOutbox)["failed"] == 1
        assert dispatch_tickets(db_session, publish).published == 1
        assert dispatch_bookings(db_session, publish).published == 1
        db_session.refresh(booking)
        assert booking.delivery_attempts == 2
        assert booking.last_error is None
        assert client.get("/metrics").json()["events_received_total"] == 2

        # A crash after receipt but before marking published sends the same ID again.
        ticket.published_at = None
        db_session.commit()
        assert dispatch_tickets(db_session, publish).published == 1
        assert client.get("/metrics").json()["events_received_total"] == 2

        received = client.get(
            f"/v1/events/{ticket.id}",
            headers={"X-Internal-Service-Token": "local-test-token"},
        ).json()
    assert received["correlation_id"] == "chat-turn-42"
    assert "owner_id" not in received["payload"]


def test_worker_runs_both_domain_outboxes(db_session, test_user):
    ticket_service.create_ticket(
        db_session, test_user.id, TicketCreate(content="VPN", description="Cannot connect"),
    )
    booking_service.create_booking(
        db_session, test_user.id,
        BookingCreate(reason="Review", time="2030-02-01T09:00:00+07:00"),
    )
    sessions = sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)
    delivered = []
    result = run_once(sessions, sessions, delivered.append)
    assert result["ticket"]["published"] == 1
    assert result["booking"]["published"] == 1
    assert result["ticket"]["pending"] == result["booking"]["pending"] == 0
    assert {event.producer for event in delivered} == {"ticket-service", "booking-service"}
