from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared_platform.api_protection import install_api_protection


def test_limits_auth_errors_and_request_ids(monkeypatch, auth_headers):
    monkeypatch.setenv("API_MAX_BODY_BYTES", "20")
    monkeypatch.setenv("API_RATE_LIMIT_PER_MINUTE", "3")
    app = FastAPI()

    @app.post('/tickets/')
    def create(body: dict):
        return body

    install_api_protection(app, 'business')
    with TestClient(app) as client:
        preflight = client.options('/tickets/', headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "Authorization"})
        assert preflight.status_code == 200
        assert preflight.headers['access-control-allow-origin'] == 'http://localhost:5173'
        assert client.options('/tickets/', headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "POST"}).status_code == 400
        assert client.post('/tickets/', json={}).status_code == 401
        assert client.get('/internal').status_code == 404
        big = client.post('/tickets/', content=b'x' * 21, headers=auth_headers)
        assert big.status_code == 413
        response = client.post('/tickets/', json={"ok": True}, headers={**auth_headers, 'X-Request-ID': 'test-123'})
        assert response.json() == {"ok": True}
        assert response.headers['X-Request-ID'] == 'test-123'
        malformed = client.post('/tickets/', content='invalid', headers=auth_headers)
        assert malformed.status_code == 422
        assert malformed.json()['correlation_id'] == malformed.headers['X-Request-ID']
        limited = client.post('/tickets/', json={}, headers=auth_headers)
        assert limited.status_code == 429
        assert limited.headers['Retry-After'] == '60'


def test_chunked_body_is_bounded_and_negative_subject_rejected(auth_headers):
    from utils.security import create_access_token
    app = FastAPI()
    install_api_protection(app, 'chat')
    with TestClient(app) as client:
        response = client.post('/v1/chat/messages', content=iter([b'x' * 600000, b'x' * 600000]), headers=auth_headers)
        assert response.status_code == 413
        token = create_access_token(data={"sub": "-1"})
        assert client.post('/v1/chat/messages', json={}, headers={"Authorization": f"Bearer {token}"}).status_code == 401
