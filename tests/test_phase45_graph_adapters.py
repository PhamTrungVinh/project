from shared_platform.auth_claims import AuthClaims
from tools import booking_tools, ticket_tools


def test_ticket_graph_create_uses_claim_authenticated_adapter(monkeypatch, db_session, test_user):
    calls = []

    def remote(url, claims, method, path, payload=None, query=None, idempotency_key=None):
        calls.append((url, claims, method, path, payload, idempotency_key))
        return {"ticket_code": "TCK-REMOTE"}

    monkeypatch.setattr(ticket_tools, "TICKET_ADAPTER", "http")
    monkeypatch.setattr(ticket_tools, "domain_request_for_claims", remote)
    monkeypatch.setattr(ticket_tools, "remember_episode", lambda *args: None)
    claims = AuthClaims(subject_id=test_user.id, email=test_user.email, full_name=test_user.full_name)
    create_ticket = ticket_tools.build_ticket_tools(test_user.id, "thread-1", "idem-1", claims)[0]

    result = create_ticket.invoke({"content": "VPN", "description": "Cannot connect"})

    assert result == "Created ticket TCK-REMOTE, status: Pending."
    _, forwarded_claims, method, path, payload, key = calls[0]
    assert (forwarded_claims.subject_id, method, path, key) == (test_user.id, "POST", "/tickets/", "idem-1")
    assert payload["customer_name"] == test_user.full_name
    assert payload["email"] == test_user.email


def test_booking_graph_create_uses_claim_authenticated_adapter(monkeypatch, db_session, test_user):
    calls = []

    def remote(url, claims, method, path, payload=None, query=None, idempotency_key=None):
        calls.append((claims, method, path, payload, idempotency_key))
        return {"booking_code": "BKG-REMOTE"}

    monkeypatch.setattr(booking_tools, "BOOKING_ADAPTER", "http")
    monkeypatch.setattr(booking_tools, "domain_request_for_claims", remote)
    monkeypatch.setattr(booking_tools, "remember_episode", lambda *args: None)
    claims = AuthClaims(subject_id=test_user.id, email=test_user.email, full_name=test_user.full_name)
    book_room = booking_tools.build_booking_tools(test_user.id, "thread-1", "idem-2", claims)[0]

    result = book_room.invoke({"reason": "Planning", "time": "2026-10-01T09:00:00"})

    assert result == "Booked room, booking_code: BKG-REMOTE, status: Scheduled."
    forwarded_claims, method, path, payload, key = calls[0]
    assert (forwarded_claims.subject_id, method, path, key) == (test_user.id, "POST", "/bookings/", "idem-2")
    assert payload["customer_name"] == test_user.full_name
