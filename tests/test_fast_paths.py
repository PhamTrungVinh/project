import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from langchain_core.messages import HumanMessage
from sqlalchemy import event

from guardrail import guardrail_node
from memory_service.models import EpisodicMemory, SemanticMemory
from services import chat_service
from services.memory_service import recall_episodes, recall_facts
from utils.intent import is_standalone_pleasantry


def test_standalone_pleasantry_is_detected_without_an_llm():
    assert is_standalone_pleasantry("hello!")
    assert is_standalone_pleasantry("thank you")
    assert not is_standalone_pleasantry("hello, create a ticket")


def test_guardrail_allows_a_standalone_pleasantry_without_calling_llm(monkeypatch):
    monkeypatch.setattr("guardrail.guardrail_llm", None)

    assert guardrail_node({"messages": [HumanMessage(content="hello")]}) == {"blocked": False}


def test_empty_memory_does_not_load_embeddings(db_session, test_user, monkeypatch):
    def fail_if_called(_: str):
        raise AssertionError("embeddings should not load for an empty memory store")

    monkeypatch.setattr("services.memory_service.embed_text", fail_if_called)
    assert recall_facts(db_session, test_user.id, "hello") == []
    assert recall_episodes(db_session, test_user.id, "hello") == []


def test_memory_lookup_filters_expired_rows_without_writing(db_session, test_user, monkeypatch):
    expired = datetime.now(timezone.utc) - timedelta(days=1)
    db_session.add_all([
        SemanticMemory(owner_id=test_user.id, fact="expired fact", embedding=json.dumps([1.0]), expires_at=expired),
        SemanticMemory(owner_id=test_user.id, fact="active fact", embedding=json.dumps([1.0])),
        EpisodicMemory(owner_id=test_user.id, thread_id="old", summary="expired episode",
                       outcome="old", embedding=json.dumps([1.0]), expires_at=expired),
        EpisodicMemory(owner_id=test_user.id, thread_id="new", summary="active episode",
                       outcome="new", embedding=json.dumps([1.0])),
    ])
    db_session.commit()
    monkeypatch.setattr("services.memory_service.embed_text", lambda _: [1.0])
    statements = []

    def record_sql(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", record_sql)
    try:
        assert recall_facts(db_session, test_user.id, "hello") == ["active fact"]
        assert recall_episodes(db_session, test_user.id, "hello") == [
            {"summary": "active episode", "outcome": "new"}
        ]
    finally:
        event.remove(engine, "before_cursor_execute", record_sql)
    assert not any(statement.lstrip().upper().startswith("DELETE") for statement in statements)


@pytest.mark.parametrize("failure", [TimeoutError("timed out"), HTTPException(status_code=503)])
def test_chat_continues_when_optional_remote_memory_fails(db_session, test_user, monkeypatch, failure):
    monkeypatch.setattr(chat_service, "MEMORY_ADAPTER", "http")

    def fail(*_args):
        raise failure

    monkeypatch.setattr(chat_service, "remote_memory_context", fail)
    assert chat_service._load_memory_context(db_session, test_user, "hello") == ""
