import pytest

from services import pending_action_service
from utils.exceptions import ConflictException, NotFoundException


def test_ticket_idempotency_replays_original_response(client, auth_headers):
    headers = {**auth_headers, "Idempotency-Key": "ticket-create-1"}
    payload = {"content": "VPN issue", "description": "Cannot connect"}
    first = client.post("/tickets/", json=payload, headers=headers)
    second = client.post("/tickets/", json=payload, headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["ticket_code"] == second.json()["ticket_code"]


def test_ticket_idempotency_rejects_changed_payload(client, auth_headers):
    headers = {**auth_headers, "Idempotency-Key": "ticket-conflict-1"}
    assert client.post("/tickets/", json={"content": "A", "description": "B"}, headers=headers).status_code == 200
    assert client.post("/tickets/", json={"content": "Changed", "description": "B"}, headers=headers).status_code == 409


def _action(db, owner_id, thread_id="thread-a", ttl=600):
    return pending_action_service.create(db, owner_id, thread_id, "ticket", {"id": "call-1", "name": "create_ticket", "args": {"content": "A", "description": "B"}}, "Confirm?", ttl)


def test_pending_action_expires(db_session, test_user):
    action = _action(db_session, test_user.id, ttl=-1)
    assert pending_action_service.active_tasks(db_session, test_user.id, "thread-a") == []
    assert action.status == "expired"


def test_pending_action_decision_is_retry_safe(db_session, test_user):
    action = _action(db_session, test_user.id)
    assert pending_action_service.decide(db_session, test_user.id, "thread-a", action.id, True).status == "approved"
    assert pending_action_service.decide(db_session, test_user.id, "thread-a", action.id, True).status == "approved"


def test_pending_action_owner_and_thread_are_isolated(db_session, test_user, test_user_2):
    action = _action(db_session, test_user.id)
    with pytest.raises(NotFoundException):
        pending_action_service.decide(db_session, test_user_2.id, "thread-a", action.id, True)
    with pytest.raises(NotFoundException):
        pending_action_service.decide(db_session, test_user.id, "other-thread", action.id, True)
