import json

import pytest

from models.ticket import TicketAudit, TicketOutbox, TicketStatus
from utils.exceptions import ConflictException
from schemas.ticket import TicketCreate
from services import ticket_service
from services.ticket_outbox_service import dispatch_pending


def test_ticket_create_writes_audit_and_outbox_in_the_same_transaction(db_session, test_user):
    ticket = ticket_service.create_ticket(
        db_session,
        test_user.id,
        TicketCreate(content="VPN unavailable", description="Cannot connect from home"),
        idempotency_key="phase4-ticket-create",
    )

    audit = db_session.query(TicketAudit).one()
    outbox = db_session.query(TicketOutbox).one()
    assert audit.ticket_id == ticket.id
    assert audit.owner_id == test_user.id
    assert audit.action == "TicketCreated"
    assert json.loads(outbox.payload_json)["ticket_code"] == ticket.ticket_code
    assert outbox.event_type == "TicketCreated"


def test_ticket_status_transitions_are_enforced_and_audited(db_session, test_user):
    ticket = ticket_service.create_ticket(
        db_session,
        test_user.id,
        TicketCreate(content="Laptop problem", description="Screen flickers"),
    )

    with pytest.raises(ConflictException, match="Invalid ticket status transition"):
        ticket_service.update_ticket_status(
            db_session, test_user.id, ticket.ticket_code, TicketStatus.FINISHED
        )

    updated = ticket_service.update_ticket_status(
        db_session, test_user.id, ticket.ticket_code, TicketStatus.RESOLVING
    )
    assert updated.status == TicketStatus.RESOLVING

    audits = db_session.query(TicketAudit).order_by(TicketAudit.id).all()
    events = db_session.query(TicketOutbox).order_by(TicketOutbox.occurred_at).all()
    assert [audit.action for audit in audits] == ["TicketCreated", "TicketUpdated"]
    assert json.loads(audits[-1].details_json)["previous_status"] == "Pending"


def test_idempotency_replay_does_not_duplicate_ticket_events(db_session, test_user):
    data = TicketCreate(content="VPN unavailable", description="Cannot connect from home")
    first = ticket_service.create_ticket(
        db_session, test_user.id, data, idempotency_key="ticket-event-replay"
    )
    second = ticket_service.create_ticket(
        db_session, test_user.id, data, idempotency_key="ticket-event-replay"
    )

    assert first.ticket_code == second["ticket_code"]
    assert db_session.query(TicketAudit).count() == 1
    assert db_session.query(TicketOutbox).count() == 1


def test_ticket_creation_uses_authenticated_contact(client, auth_headers, test_user):
    response = client.post(
        "/tickets/",
        json={
            "content": "VPN unavailable",
            "description": "Cannot connect from home",
            "customer_name": "Spoofed Name",
            "email": "spoofed@example.com",
        },
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["customer_name"] == test_user.full_name
    assert response.json()["email"] == test_user.email


def test_ticket_outbox_dispatch_retries_failed_events(db_session, test_user):
    ticket_service.create_ticket(
        db_session,
        test_user.id,
        TicketCreate(content="VPN unavailable", description="Cannot connect from home"),
    )
    event = db_session.query(TicketOutbox).one()
    delivered = []

    result = dispatch_pending(db_session, delivered.append)
    db_session.refresh(event)
    assert result.published == 1
    assert result.failed == 0
    assert delivered[0].event_id == event.id
    assert event.delivery_attempts == 1
    assert event.published_at is not None

    ticket_service.create_ticket(
        db_session,
        test_user.id,
        TicketCreate(content="Laptop issue", description="Screen flickers"),
    )
    failed_event = db_session.query(TicketOutbox).filter(TicketOutbox.published_at.is_(None)).one()

    def fail_publish(_):
        raise RuntimeError("broker unavailable")

    failed = dispatch_pending(db_session, fail_publish)
    db_session.refresh(failed_event)
    assert failed.published == 0
    assert failed.failed == 1
    assert failed_event.delivery_attempts == 1
    assert failed_event.last_error == "broker unavailable"

    retried = dispatch_pending(db_session, delivered.append)
    db_session.refresh(failed_event)
    assert retried.published == 1
    assert failed_event.delivery_attempts == 2
    assert failed_event.published_at is not None
