import asyncio
import json
from threading import Event
from types import SimpleNamespace

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langgraph.graph import END, START, StateGraph

from chat_orchestrator import app as orchestrator_app, routes
from database import get_db
from crud import conversation as conv_crud
from schemas.chat import ChatMessageResponse
from services import chat_service, chat_stream_service, knowledge_service, pending_action_service
from shared_platform.api_contracts import KnowledgeQueryRequest
from shared_platform.auth_claims import AuthClaims
from state import AgentState


def _events(response):
    events = []
    for frame in response.text.split("\n\n"):
        if frame.startswith("event:"):
            name, payload = frame.split("\n", 1)
            events.append((name.removeprefix("event: "), json.loads(payload.removeprefix("data: "))))
    return events


def test_stream_returns_answer_deltas_and_pending_actions(client, auth_headers, test_user, db_session, monkeypatch):
    action = pending_action_service.create(db_session, test_user.id, "sse-thread", "ticket",
        {"name": "create_ticket", "args": {"content": "VPN"}, "id": "sse-call"}, "Create a ticket?", 600)

    def send(db, user, thread, message, *, on_delta):
        assert db is not db_session
        assert user.subject_id == test_user.id
        on_delta("Please ")
        on_delta("confirm.\nXin chào")
        return {"answer": "Please confirm.\nXin chào", "route": "ticket", "thread_id": thread}

    monkeypatch.setattr(routes.chat_service, "send_message", send)
    response = client.post("/v1/chat/messages/stream", headers={**auth_headers, "X-Request-ID": "sse-trace"},
        json={"message": "Create a ticket", "thread_id": "sse-thread"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    events = _events(response)
    assert [name for name, _ in events] == ["start", "delta", "delta", "result"]
    assert "".join(data["text"] for name, data in events if name == "delta") == events[-1][1]["answer"]
    assert events[0][1] == {"thread_id": "sse-thread", "correlation_id": "sse-trace"}
    assert events[-1][1]["pending_actions"][0]["id"] == action.id
    assert events[-1][1]["answer"] == "Please confirm.\nXin chào"


def test_stream_requires_authentication_and_valid_body(client, auth_headers):
    assert client.post("/v1/chat/messages/stream", json={"message": "Hi"}).status_code == 401
    assert client.post("/v1/chat/messages/stream", headers=auth_headers, json={"message": ""}).status_code == 422


def test_stream_rejects_other_owner_before_headers(client, auth_headers_user_2, test_user, db_session, monkeypatch):
    conv_crud.create_conversation(db_session, test_user.id, "private-thread")
    monkeypatch.setattr(routes.chat_service, "send_message", lambda *a, **k: 1 / 0)
    response = client.post("/v1/chat/messages/stream", headers=auth_headers_user_2,
                           json={"message": "Hi", "thread_id": "private-thread"})
    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/json")


def test_stream_failure_is_sanitized_and_terminal(client, auth_headers, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("secret provider credential")

    monkeypatch.setattr(routes.chat_service, "send_message", fail)
    response = client.post("/v1/chat/messages/stream", headers=auth_headers, json={"message": "Hi"})
    events = _events(response)
    assert [name for name, _ in events] == ["start", "error"]
    assert events[-1][1]["status"] == 500
    assert "secret provider credential" not in response.text


def test_standalone_stream_passes_request_protection(db_session, auth_headers, monkeypatch):
    def override_db():
        yield db_session

    def send(db, user, thread, message, *, on_delta):
        on_delta("Hello")
        return {"answer": "Hello", "route": "it_support", "thread_id": thread}

    app = orchestrator_app.app
    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(orchestrator_app, "get_app", lambda: object())
    monkeypatch.setattr(orchestrator_app, "get_knowledge_adapter", lambda: object())
    monkeypatch.setattr(routes.chat_service, "send_message", send)
    try:
        with TestClient(app) as client:
            response = client.post("/v1/chat/messages/stream", headers=auth_headers, json={"message": "Hi"})
            assert response.status_code == 200
            assert _events(response)[-1][1]["answer"] == "Hello"
            assert response.headers["x-request-id"] == _events(response)[0][1]["correlation_id"]
            assert client.post("/v1/chat/messages/stream", json={"message": "Hi"}).status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_graph_stream_excludes_routing_reasoning_and_tool_arguments(db_session, test_user, monkeypatch):
    class Graph:
        def stream(self, state, *, config, stream_mode):
            assert stream_mode == ["messages", "custom", "values"]
            assert config["configurable"]["stream_answer"] is True
            yield "values", {"messages": [AIMessage(content="old answer")]}
            for node in ["router", "guardrail", "supervisor"]:
                yield "messages", (AIMessageChunk(content="private prompt"), {"langgraph_node": node})
            yield "messages", (AIMessageChunk(content="", tool_call_chunks=[{
                "name": "create_ticket", "args": '{"private":"value"}', "id": "call", "index": 0,
            }]), {"langgraph_node": "ticket_agent"})
            yield "messages", (AIMessageChunk(content="Final "), {"langgraph_node": "ticket_agent"})
            yield "custom", {"type": "answer", "text": "answer"}
            yield "values", {"messages": [AIMessage(content="Final answer")], "route": "faq"}

    monkeypatch.setattr(chat_service, "get_app", lambda: Graph())
    monkeypatch.setattr(chat_service, "_load_memory_context", lambda *args: "")
    deltas = []
    result = chat_service.send_message(db_session, AuthClaims(subject_id=test_user.id), "graph-sse", "Hello",
                                       on_delta=deltas.append)
    assert result["answer"] == "Final answer"
    assert deltas == ["Final ", "answer"]


def test_real_graph_invocation_streams_model_chunks(db_session, test_user, monkeypatch):
    llm = FakeListChatModel(responses=["**Xin chào**"])
    workflow = StateGraph(AgentState)
    workflow.add_node("it_support_agent", lambda state: {"messages": [llm.invoke(state["messages"])]})
    workflow.add_edge(START, "it_support_agent")
    workflow.add_edge("it_support_agent", END)
    graph = workflow.compile()
    monkeypatch.setattr(chat_service, "get_app", lambda: graph)
    monkeypatch.setattr(chat_service, "_load_memory_context", lambda *args: "")
    deltas = []
    result = chat_service.send_message(db_session, AuthClaims(subject_id=test_user.id), "live-text", "Hello",
                                      on_delta=deltas.append)
    assert len(deltas) > 1
    assert "".join(deltas) == result["answer"] == "**Xin chào**"


def test_faq_provider_stream_emits_text_and_closes_connection(monkeypatch):
    emitted, calls = [], []

    class ProviderStream:
        closed = False

        def __iter__(self):
            for text in ["Leave ", "is ", "12 days."]:
                yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])

        def close(self):
            self.closed = True

    stream = ProviderStream()

    def create(**kwargs):
        calls.append(kwargs)
        return stream

    document = SimpleNamespace(page_content="Annual leave is 12 days.", metadata={"source": "HR.pdf", "page": 1})
    monkeypatch.setattr(knowledge_service, "get_raw_groq_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    monkeypatch.setattr(knowledge_service, "get_embeddings", lambda: object())
    monkeypatch.setattr(knowledge_service, "build_rag_resources", lambda: {"bm25": None, "dense": None, "reranker": None})
    monkeypatch.setattr(knowledge_service, "hyde_query", lambda query, client: query)
    monkeypatch.setattr(knowledge_service, "hybrid_retrieve", lambda *args, **kwargs: [document])
    monkeypatch.setattr(knowledge_service, "rerank", lambda *args, **kwargs: [document])
    monkeypatch.setattr(knowledge_service, "mmr_select", lambda *args, **kwargs: [document])
    monkeypatch.setattr(knowledge_service, "get_answer_writer", lambda: emitted.append)
    response = knowledge_service.LocalKnowledgeAdapter().query(KnowledgeQueryRequest(
        query="How much leave?", requester=AuthClaims(subject_id=1), correlation_id="faq-stream"))
    assert calls[0]["stream"] is True
    assert emitted == ["Leave ", "is ", "12 days."]
    assert response.answer == "".join(emitted)
    assert response.citations == ["HR.pdf (page 2)"]
    assert stream.closed


def test_static_reply_stream_preserves_word_spacing():
    async def consume():
        async def run():
            return [frame async for frame in chat_stream_service.stream_turn(
                lambda on_delta: ChatMessageResponse(answer="Please confirm.\nXin chào", route="ticket",
                    thread_id="static", pending_actions=[], correlation_id="trace"), "static", "trace")]

        frames = await run()
        deltas = [json.loads(frame.split("data: ", 1)[1])["text"] for frame in frames if frame.startswith("event: delta")]
        assert len(deltas) > 1
        assert "".join(deltas) == "Please confirm.\nXin chào"
        assert all("progress" not in frame for frame in frames)

    asyncio.run(consume())


def test_heartbeat_and_disconnect_allow_worker_to_finish(monkeypatch):
    monkeypatch.setattr(chat_stream_service, "HEARTBEAT_SECONDS", 0.01)
    entered, release, finished = Event(), Event(), Event()

    def run(on_delta):
        entered.set()
        assert release.wait(2)
        on_delta("Done")
        finished.set()
        return ChatMessageResponse(answer="Done", thread_id="disconnect", route="faq",
                                   pending_actions=[], correlation_id="trace")

    async def consume():
        stream = chat_stream_service.stream_turn(run, "disconnect", "trace")
        assert "event: start" in await anext(stream)
        assert await anext(stream) == ": keep-alive\n\n"
        assert entered.is_set()
        await stream.aclose()
        release.set()
        assert await asyncio.to_thread(finished.wait, 2)

    asyncio.run(consume())
