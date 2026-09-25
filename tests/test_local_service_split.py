import sqlite3

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from database import Base
from identity_service.app import app as identity_app
from models.conversation import Conversation
from models.user import User
from scripts.split_local_databases import split
from shared_platform.auth_claims import AuthClaims
from services import booking_service, ticket_service
from schemas.booking import BookingCreate
from schemas.ticket import TicketCreate
from tools import booking_tools, ticket_tools


def test_identity_api_uses_only_its_owned_store(tmp_path, monkeypatch):
    from identity_service import app as identity_module

    engine = create_engine(f"sqlite:///{tmp_path / 'identity.db'}")
    Base.metadata.create_all(engine, tables=[User.__table__])
    monkeypatch.setattr(identity_module, "engine", engine)

    def identity_db():
        with Session(engine) as db:
            yield db

    identity_app.dependency_overrides[identity_module.get_db] = identity_db
    try:
        with TestClient(identity_app) as client:
            created = client.post("/auth/register", json={"email": "isolated@example.com", "password": "Password123!", "full_name": "Isolated"})
            assert created.status_code == 200
            login = client.post("/auth/login", data={"username": "isolated@example.com", "password": "Password123!"})
            assert login.status_code == 200
            me = client.get("/users/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"})
            assert me.status_code == 200
            assert me.json()["email"] == "isolated@example.com"
        with sqlite3.connect(tmp_path / "identity.db") as db:
            assert {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")} == {"users"}
    finally:
        identity_app.dependency_overrides[identity_module.get_db] = identity_module.identity_db
        engine.dispose()


def test_domain_create_with_claims_does_not_query_identity(tmp_path):
    claims = AuthClaims(subject_id=7, email="owner@example.com", full_name="Owner")
    for model, service, data in (
        ("ticket", ticket_service, TicketCreate(content="Issue", description="Description")),
        ("booking", booking_service, BookingCreate(reason="Meeting", time="2026-09-24T10:00:00")),
    ):
        engine = create_engine(f"sqlite:///{tmp_path / (model + '.db')}")
        names = ("tickets", "ticket_audit", "ticket_outbox", "idempotency_records") if model == "ticket" else ("bookings", "booking_audit", "booking_outbox", "idempotency_records")
        Base.metadata.create_all(engine, tables=[Base.metadata.tables[name] for name in names])
        with Session(engine) as db:
            result = service.create_ticket(db, 7, data, claims=claims) if model == "ticket" else service.create_booking(db, 7, data, claims=claims)
            assert result.email == claims.email
        engine.dispose()


def test_split_copies_owned_rows_without_modifying_source(tmp_path):
    source = tmp_path / "app.db"
    engine = create_engine(f"sqlite:///{source}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(User(id=4, email="old@example.com", hashed_password="hash"))
        db.add(Conversation(thread_id="session-old", owner_id=4))
        db.commit()
    engine.dispose()
    output = tmp_path / "split"
    counts = split(source, output)
    assert counts["identity_service.db:users"] == 1
    assert counts["chat_service.db:conversations"] == 1
    with sqlite3.connect(output / "chat_service.db") as db:
        assert db.execute("PRAGMA foreign_key_list(conversations)").fetchall() == []
        assert db.execute("SELECT owner_id FROM conversations").fetchone() == (4,)
    with sqlite3.connect(source) as db:
        assert db.execute("SELECT email FROM users").fetchone() == ("old@example.com",)


def test_http_chat_tools_never_open_the_chat_database(monkeypatch):
    claims = AuthClaims(subject_id=9, email="owner@example.com", full_name="Owner")

    def forbidden_db():
        raise AssertionError("HTTP tool opened the chat database")

    monkeypatch.setattr(ticket_tools, "TICKET_ADAPTER", "http")
    monkeypatch.setattr(booking_tools, "BOOKING_ADAPTER", "http")
    monkeypatch.setattr(ticket_tools, "get_db_session", forbidden_db)
    monkeypatch.setattr(booking_tools, "get_db_session", forbidden_db)
    monkeypatch.setattr(ticket_tools, "record_memory_episode", lambda *_args: None)
    monkeypatch.setattr(booking_tools, "record_memory_episode", lambda *_args: None)
    monkeypatch.setattr(ticket_tools, "domain_request_for_claims", lambda *_args, **_kwargs: {"ticket_code": "TCK-9"})
    monkeypatch.setattr(booking_tools, "domain_request_for_claims", lambda *_args, **_kwargs: {"booking_code": "BKG-9"})
    ticket_set = ticket_tools.build_ticket_tools(9, "thread", claims=claims)
    booking_set = booking_tools.build_booking_tools(9, "thread", claims=claims)
    ticket = ticket_set[0].invoke({"content": "VPN", "description": "Down"})
    booking = booking_set[0].invoke({"reason": "Meeting", "time": "2026-09-24T10:00:00"})
    assert "TCK-9" in ticket
    assert "BKG-9" in booking
    assert "Updated ticket" in ticket_set[2].invoke({"ticket_code": "TCK-9", "content": "Fixed"})
    assert "status changed" in ticket_set[3].invoke({"ticket_code": "TCK-9", "status": "Resolving"})
    assert "Updated booking" in booking_set[2].invoke({"booking_code": "BKG-9", "reason": "Changed"})
    assert "Canceled booking" in booking_set[3].invoke({"booking_code": "BKG-9"})
