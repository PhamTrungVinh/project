from datetime import datetime, timedelta, timezone
from threading import Event, Thread

from chat_orchestrator import routes
from services import pending_action_service
from services.thread_lock import thread_turn_lock


def _action(db_session, owner_id, thread_id="thread-1"):
    return pending_action_service.create(
        db_session, owner_id, thread_id, "ticket",
        {"name": "create_ticket", "args": {"content": "VPN", "description": "Cannot connect"}, "id": "call-1"},
        "Create a ticket?", 600,
    )


def test_versioned_chat_returns_pending_action_and_correlation(
    client, auth_headers, test_user, db_session, monkeypatch,
):
    _action(db_session, test_user.id)
    def send_message(db, user, thread, message):
        assert user.subject_id == test_user.id
        return {"answer": "Please confirm.", "route": "ticket", "thread_id": thread}

    monkeypatch.setattr(routes.chat_service, "send_message", send_message)
    response = client.post(
        "/v1/chat/messages", json={"message": "Open a ticket", "thread_id": "thread-1"},
        headers={**auth_headers, "X-Request-ID": "trace-123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["route"] == "ticket"
    assert body["correlation_id"] == "trace-123"
    assert body["pending_actions"][0]["question"] == "Create a ticket?"
    assert response.headers["X-Request-ID"] == "trace-123"


def test_decision_approves_once_and_replays_result(
    client, auth_headers, test_user, db_session, monkeypatch,
):
    action = _action(db_session, test_user.id)
    calls = []

    def execute(*args, **kwargs):
        calls.append((args, kwargs))
        return "Ticket TCK-1 created"

    monkeypatch.setattr(routes, "execute_confirmed_tool_call", execute)
    payload = {"decision": "approve"}
    url = f"/v1/pending-actions/{action.id}/decision"
    first = client.post(url, json=payload, headers=auth_headers)
    second = client.post(url, json=payload, headers=auth_headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == second.json()["status"] == "executed"
    assert first.json()["result"] == second.json()["result"] == "Ticket TCK-1 created"
    assert len(calls) == 1
    assert calls[0][0][4] == action.idempotency_key
    assert calls[0][1]["raise_errors"] is True


def test_decision_uses_persisted_owner_and_thread(
    client, auth_headers, auth_headers_user_2, test_user, db_session, monkeypatch,
):
    action = _action(db_session, test_user.id)
    monkeypatch.setattr(routes, "execute_confirmed_tool_call", lambda *a, **kw: "done")
    url = f"/v1/pending-actions/{action.id}/decision"
    assert client.post(url, json={"decision": "approve"},
                       headers=auth_headers_user_2).status_code == 404
    assert client.post(url, json={"decision": "approve", "thread_id": "another-thread"},
                       headers=auth_headers).status_code == 422
    db_session.refresh(action)
    assert action.status == "pending"
    response = client.post(url, json={"decision": "approve"}, headers=auth_headers)
    assert response.json()["thread_id"] == "thread-1"


def test_reject_replays_and_conflicting_approval_fails(client, auth_headers, test_user, db_session):
    action = _action(db_session, test_user.id)
    url = f"/v1/pending-actions/{action.id}/decision"
    payload = {"decision": "reject"}
    assert client.post(url, json=payload, headers=auth_headers).json()["status"] == "rejected"
    assert client.post(url, json=payload, headers=auth_headers).json()["status"] == "rejected"
    assert client.post(url, json={"decision": "approve"},
                       headers=auth_headers).status_code == 409


def test_expired_action_never_executes(client, auth_headers, test_user, db_session, monkeypatch):
    action = _action(db_session, test_user.id)
    action.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    monkeypatch.setattr(routes, "execute_confirmed_tool_call", lambda *a, **kw: 1 / 0)
    url = f"/v1/pending-actions/{action.id}/decision"
    response = client.post(url, json={"decision": "approve"},
                           headers=auth_headers)
    assert response.status_code == 409
    db_session.refresh(action)
    assert action.status == "expired"


def test_previously_approved_action_can_resume(client, auth_headers, test_user, db_session, monkeypatch):
    action = _action(db_session, test_user.id)
    action.status = "approved"
    db_session.commit()
    monkeypatch.setattr(routes, "execute_confirmed_tool_call", lambda *a, **kw: "resumed")
    response = client.post(
        f"/v1/pending-actions/{action.id}/decision",
        json={"decision": "approve"}, headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["result"] == "resumed"


def test_failed_execution_can_be_retried(client, auth_headers, test_user, db_session, monkeypatch):
    action = _action(db_session, test_user.id)
    calls = 0

    def execute(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("temporary failure")
        return "done"

    monkeypatch.setattr(routes, "execute_confirmed_tool_call", execute)
    url = f"/v1/pending-actions/{action.id}/decision"
    payload = {"decision": "approve"}
    try:
        client.post(url, json=payload, headers=auth_headers)
    except RuntimeError:
        pass
    db_session.refresh(action)
    assert action.status == "pending"
    response = client.post(url, json=payload, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["result"] == "done"
    assert calls == 2


def test_same_thread_turns_are_serialized():
    entered = Event()
    finished = Event()

    def competing_turn():
        with thread_turn_lock(1, "same-thread"):
            entered.set()
        finished.set()

    with thread_turn_lock(1, "same-thread"):
        worker = Thread(target=competing_turn)
        worker.start()
        assert not entered.wait(0.1)
    assert finished.wait(1)
    worker.join()
