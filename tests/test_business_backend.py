"""Exercise the combined HTTP API against three physically separate stores."""
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from business_backend import app as backend
from service_migrations.common import owned_metadata
from shared_platform.domain_persistence import session_factory_for


@pytest.fixture
def business_client(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTBOX_WORKER_ENABLED", "false")
    session_factory_for.cache_clear()
    engines = {}
    for domain in ("identity", "ticket", "booking", "event"):
        monkeypatch.setenv(f"{domain.upper()}_DATABASE_URL", f"sqlite:///{tmp_path / (domain + '.db')}")
        engine = session_factory_for(domain).kw["bind"]
        owned_metadata(domain).create_all(engine)
        engines[domain] = engine
    try:
        with TestClient(backend.app) as client:
            yield client, engines
    finally:
        for engine in engines.values():
            engine.dispose()
        session_factory_for.cache_clear()


def register(client, email):
    result = client.post('/auth/register', json={"email": email, "password": "Password123!", "full_name": "Owner"})
    assert result.status_code == 200
    result = client.post('/auth/login', data={"username": email, "password": "Password123!"})
    assert result.status_code == 200
    return {"Authorization": f"Bearer {result.json()['access_token']}"}


def test_combined_api_preserves_stores_ownership_and_retries(business_client):
    client, engines = business_client
    owner = register(client, 'owner@example.com')
    other = register(client, 'other@example.com')
    assert client.get('/users/me', headers=owner).json()['email'] == 'owner@example.com'
    assert client.get('/users/me').status_code == 401
    assert client.post('/auth/login', data={"username": "owner@example.com", "password": "wrong"}).status_code == 401
    assert client.post('/auth/register', json={"email": "owner@example.com", "password": "Password123!"}).status_code == 409
    assert client.get('/ready').json() == {"status": "ready"}

    for domain, payload, code_key in (
        ('ticket', {"content": "VPN", "description": "Unavailable", "email": "spoof@example.com"}, 'ticket_code'),
        ('booking', {"reason": "Planning", "time": "2030-10-01T09:00:00+07:00", "email": "spoof@example.com"}, 'booking_code'),
    ):
        path = f'/{domain}s/'
        headers = {**owner, "Idempotency-Key": "same-key-across-domains", "X-Request-ID": "business-test"}
        assert client.get(path).status_code == 401
        response = client.post(path, json=payload, headers=headers)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result['email'] == 'owner@example.com'
        assert response.headers['X-Request-ID'] == 'business-test'
        assert client.post(path, json=payload, headers=headers).json() == result
        changed = {**payload, ('content' if domain == 'ticket' else 'reason'): 'Changed'}
        assert client.post(path, json=changed, headers=headers).status_code == 409
        assert len(client.get(path, headers=owner).json()) == 1
        assert client.get(path, headers=other).json() == []
        item = path + result[code_key]
        assert client.get(item, headers=owner).status_code == 200
        assert client.get(item, headers=other).status_code in (403, 404)
        assert client.patch(item, json=changed, headers=other).status_code in (403, 404)
        with engines[domain].connect() as connection:
            assert connection.execute(text(f'SELECT count(*) FROM {domain}_outbox')).scalar() == 1
            assert connection.execute(text(f'SELECT count(*) FROM {domain}_audit')).scalar() == 1
        if domain == 'ticket':
            assert client.patch(item + '/status', json={"status": "Resolving"}, headers=owner).json()['status'] == 'Resolving'
        else:
            assert result['time'] == '2030-10-01T02:00:00+00:00'
            assert client.post(item + '/cancel', headers=other).status_code in (403, 404)
            assert client.post(item + '/cancel', headers=owner).json()['status'] == 'Canceled'

    for domain, engine in engines.items():
        assert set(inspect(engine).get_table_names()) == set(owned_metadata(domain).tables)


def test_readiness_identifies_failed_store(business_client, monkeypatch):
    client, _ = business_client
    original = backend.domain_session

    @contextmanager
    def unavailable(domain):
        if domain == 'booking':
            raise RuntimeError('database unavailable')
        with original(domain) as session:
            yield session

    monkeypatch.setattr(backend, 'domain_session', unavailable)
    assert client.get('/health').json() == {"status": "ok"}
    response = client.get('/ready')
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "booking"}


def test_local_delivery_retries_and_deduplicates_after_replay(business_client, monkeypatch):
    from business_backend import events
    client, engines = business_client
    owner = register(client, 'events@example.com')
    assert client.post('/tickets/', json={"content": "VPN", "description": "Offline"}, headers=owner).status_code == 200
    assert client.post('/bookings/', json={"reason": "Meeting", "time": "2030-10-02T09:00:00Z"}, headers=owner).status_code == 200
    original = events.publish

    def fail(event):
        raise RuntimeError('inbox offline')

    monkeypatch.setattr(events, 'publish', fail)
    result = events.deliver_once()
    assert result['ticket']['failed_this_run'] == result['booking']['failed_this_run'] == 1
    monkeypatch.setattr(events, 'publish', original)
    assert events.deliver_once()['ticket']['published'] == 1
    with engines['ticket'].begin() as db:
        db.execute(text('UPDATE ticket_outbox SET published_at = NULL'))
    assert events.deliver_once()['ticket']['published'] == 1
    with engines['event'].connect() as db:
        assert db.execute(text('SELECT count(*) FROM event_inbox')).scalar() == 2


def test_worker_lifecycle_waits_for_active_delivery(monkeypatch):
    import asyncio
    import threading
    from business_backend import events
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    monkeypatch.setenv('OUTBOX_WORKER_ENABLED', 'true')

    def deliver():
        started.set()
        assert release.wait(timeout=5)
        finished.set()

    monkeypatch.setattr(events, 'deliver_once', deliver)

    async def exercise():
        async with events.event_lifespan(None):
            assert await asyncio.to_thread(started.wait, 5)
            release.set()
        assert finished.is_set()

    asyncio.run(exercise())
