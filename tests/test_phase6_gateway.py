import httpx
from fastapi.testclient import TestClient

from gateway import app as gateway_app
from logger import request_id_context
from shared_platform import domain_http


def test_gateway_routes_chat_and_preserves_identity_and_correlation(auth_headers, monkeypatch):
    calls = []

    async def upstream(url, method, headers, body):
        calls.append((url, method, headers, body))
        return httpx.Response(200, json={"answer": "Hello", "thread_id": "t-1"})

    monkeypatch.setattr(gateway_app, "_send_upstream", upstream)
    gateway_app._request_times.clear()
    with TestClient(gateway_app.app) as client:
        response = client.post(
            "/v1/chat/messages", json={"message": "hello"},
            headers={**auth_headers, "X-Request-ID": "turn-123", "X-Authenticated-Subject": "999"},
        )
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "turn-123"
    assert calls[0][0] == f"{gateway_app.CHAT_URL}/v1/chat/messages"
    assert calls[0][2]["Authorization"] == auth_headers["Authorization"]
    assert calls[0][2]["X-Request-ID"] == "turn-123"
    assert "X-Authenticated-Subject" not in calls[0][2]


def test_gateway_rejects_invalid_identity_before_proxying(monkeypatch):
    async def upstream(*_args):
        raise AssertionError("request should not reach upstream")

    monkeypatch.setattr(gateway_app, "_send_upstream", upstream)
    gateway_app._request_times.clear()
    with TestClient(gateway_app.app) as client:
        missing = client.get("/tickets/")
        invalid = client.get("/tickets/", headers={"Authorization": "Bearer invalid"})
        unknown = client.get("/internal/admin", headers={"Authorization": "Bearer invalid"})
    assert missing.status_code == invalid.status_code == 401
    assert unknown.status_code == 404
    assert missing.json()["code"] == "unauthorized"


def test_gateway_routes_public_login_to_backend(monkeypatch):
    calls = []

    async def upstream(url, method, headers, body):
        calls.append((url, method, body))
        return httpx.Response(200, json={"access_token": "token"})

    monkeypatch.setattr(gateway_app, "_send_upstream", upstream)
    gateway_app._request_times.clear()
    with TestClient(gateway_app.app) as client:
        response = client.post("/auth/login", data={"username": "a@example.com", "password": "secret"})
    assert response.status_code == 200
    assert calls[0][0] == f"{gateway_app.BACKEND_URL}/auth/login"
    assert b"username=a%40example.com" in calls[0][2]


def test_gateway_routes_split_identity_memory_and_chat(auth_headers, monkeypatch):
    monkeypatch.setattr(gateway_app, "IDENTITY_URL", "http://identity:8007")
    monkeypatch.setattr(gateway_app, "MEMORY_URL", "http://memory:8004")
    monkeypatch.setattr(gateway_app, "CHAT_URL", "http://chat:8005")
    calls = []

    async def upstream(url, method, headers, body):
        calls.append(url)
        return httpx.Response(200, json=[])

    monkeypatch.setattr(gateway_app, "_send_upstream", upstream)
    gateway_app._request_times.clear()
    with TestClient(gateway_app.app) as client:
        assert client.get("/users/me", headers=auth_headers).status_code == 200
        assert client.get("/v1/memory/context?query=hello", headers=auth_headers).status_code == 200
        assert client.get("/v1/chat/conversations", headers=auth_headers).status_code == 200
    assert calls == [
        "http://identity:8007/users/me",
        "http://memory:8004/v1/memory/context?query=hello",
        "http://chat:8005/v1/chat/conversations",
    ]


def test_gateway_limits_body_and_request_rate(auth_headers, monkeypatch):
    calls = []

    async def upstream(*args):
        calls.append(args)
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(gateway_app, "_send_upstream", upstream)
    monkeypatch.setattr(gateway_app, "MAX_BODY_BYTES", 10)
    monkeypatch.setattr(gateway_app, "RATE_LIMIT_PER_MINUTE", 2)
    gateway_app._request_times.clear()
    with TestClient(gateway_app.app) as client:
        large = client.post("/v1/chat/messages", content=b"a" * 11, headers=auth_headers)
        first = client.get("/tickets/", headers=auth_headers)
        limited = client.get("/tickets/", headers=auth_headers)
    assert large.status_code == 413
    assert first.status_code == 200
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "60"
    assert len(calls) == 1


def test_gateway_reports_unavailable_upstream(auth_headers, monkeypatch):
    async def upstream(*_args):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(gateway_app, "_send_upstream", upstream)
    gateway_app._request_times.clear()
    with TestClient(gateway_app.app) as client:
        response = client.get("/tickets/", headers=auth_headers)
    assert response.status_code == 503
    assert response.json()["code"] == "upstream_unavailable"


def test_domain_client_forwards_correlation_id(monkeypatch):
    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"ok":true}'

    def urlopen(request, timeout):
        seen.update(dict(request.header_items()))
        return Response()

    monkeypatch.setattr(domain_http, "urlopen", urlopen)
    token = request_id_context.set("chain-123")
    try:
        assert domain_http.request_json("http://service", "GET", "/v1/items", "jwt") == {"ok": True}
    finally:
        request_id_context.reset(token)
    assert seen["X-request-id"] == "chain-123"


def test_gateway_routes_to_extracted_ticket_and_normalizes_errors(auth_headers, monkeypatch):
    calls = []

    async def upstream(url, method, headers, body):
        calls.append(url)
        return httpx.Response(404, json={"detail": "Ticket not found"})

    monkeypatch.setattr(gateway_app, "TICKET_URL", "http://ticket-service:8002")
    monkeypatch.setattr(gateway_app, "_send_upstream", upstream)
    gateway_app._request_times.clear()
    with TestClient(gateway_app.app) as client:
        response = client.get("/tickets/TCK-1", headers={**auth_headers, "X-Request-ID": "ticket-123"})
    assert calls == ["http://ticket-service:8002/tickets/TCK-1"]
    assert response.status_code == 404
    assert response.json() == {
        "detail": "Ticket not found", "code": "upstream_error", "correlation_id": "ticket-123",
    }
