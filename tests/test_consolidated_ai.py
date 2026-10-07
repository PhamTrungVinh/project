"""Composition checks using separate chat and memory stores, without AI calls."""
import asyncio

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from chat_orchestrator import app as ai_app
from memory_service.models import SemanticMemory, EpisodicMemory
from services import chat_service, memory_service
from services import domain_remote_adapter
from services.knowledge_service import LocalKnowledgeAdapter
from shared_platform.api_contracts import KnowledgeQueryRequest
from shared_platform.auth_claims import AuthClaims
from shared_platform.domain_persistence import session_factory_for


def test_memory_routes_graph_and_recording_use_owned_store(tmp_path, monkeypatch, auth_headers, auth_headers_user_2, test_user):
    memory_url = f"sqlite:///{tmp_path / 'memory.db'}"
    monkeypatch.setenv("MEMORY_DATABASE_URL", memory_url)
    monkeypatch.setattr(chat_service, "MEMORY_ADAPTER", "local")
    monkeypatch.setattr(domain_remote_adapter, "MEMORY_ADAPTER", "local")
    monkeypatch.setattr(memory_service, "embed_text", lambda _: [1.0, 0.0])
    session_factory_for.cache_clear()
    memory_engine = session_factory_for("memory").kw["bind"]
    SemanticMemory.__table__.create(memory_engine)
    EpisodicMemory.__table__.create(memory_engine)
    chat_engine = create_engine(f"sqlite:///{tmp_path / 'chat.db'}")
    try:
        # No lifespan here: this test exercises routes and store ownership only.
        client = TestClient(ai_app.app)
        assert client.post('/v1/memory/facts', json={"fact": "Prefers Python"}, headers=auth_headers).status_code == 201
        assert client.get('/v1/memory/context', params={"query": "preferences"}).status_code == 401
        assert client.get('/v1/memory/context', params={"query": "preferences"}, headers=auth_headers_user_2).json() == {"context": ""}
        with Session(chat_engine) as chat_db:
            assert "Prefers Python" in chat_service._load_memory_context(chat_db, test_user, "preferences")
        memory_service.record_episode_async(test_user.id, "thread-1", "Asked about Python", "answered").result(timeout=5)
        domain_remote_adapter.record_memory_episode(test_user, "thread-1", "Created ticket", "created")
        assert client.delete('/v1/memory', headers=auth_headers_user_2).json() == {"facts_deleted": 0, "episodes_deleted": 0}
        assert client.delete('/v1/memory', headers=auth_headers).json() == {"facts_deleted": 1, "episodes_deleted": 2}
        assert inspect(chat_engine).get_table_names() == []
    finally:
        memory_engine.dispose()
        chat_engine.dispose()
        session_factory_for.cache_clear()


def test_rag_failure_does_not_prevent_service_startup(monkeypatch):
    adapter = LocalKnowledgeAdapter()

    def fail():
        raise RuntimeError("Missing approved index")

    monkeypatch.setattr(adapter, "preload", fail)
    monkeypatch.setattr(ai_app, "get_knowledge_adapter", lambda: adapter)
    monkeypatch.setattr(ai_app, "get_app", lambda: object())
    monkeypatch.setattr(ai_app, "validate_startup_configuration", lambda: None)

    async def exercise():
        async with ai_app.lifespan(ai_app.app):
            assert adapter.startup_status == "loading"
            assert ai_app.health() == {"status": "ok"}
            request = KnowledgeQueryRequest(query="policy", requester=AuthClaims(subject_id=1), correlation_id="test")
            assert adapter.query(request).status == "unavailable"
        assert adapter.startup_status == "unavailable"
        assert adapter.query(request).status == "unavailable"

    asyncio.run(exercise())
