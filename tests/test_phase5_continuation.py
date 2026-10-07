import sqlite3

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from chat_orchestrator import app as orchestrator_app, routes
from database import get_db
from services import chat_service, pending_action_service
from shared_platform.auth_claims import AuthClaims
from state import AgentState
from utils.exceptions import ForbiddenException


def _graph(checkpoint_path):
    connection = sqlite3.connect(checkpoint_path, check_same_thread=False)
    workflow = StateGraph(AgentState)
    workflow.add_node("seed", lambda _: {})
    workflow.add_node("confirmed", lambda _: {})
    workflow.add_node("supervisor", lambda state: {
        "messages": [AIMessage(content="Ticket TCK-1 created. The leave policy answer is 12 days.")],
        "route": "done", "active_request": None,
    })
    workflow.add_edge(START, "seed")
    workflow.add_edge("seed", END)
    workflow.add_edge("confirmed", "supervisor")
    workflow.add_edge("supervisor", END)
    return workflow.compile(checkpointer=SqliteSaver(connection)), connection


def test_decision_continues_multi_request_after_restart(db_session, test_user, tmp_path, monkeypatch):
    path = str(tmp_path / "checkpoints.db")
    graph, connection = _graph(path)
    config = {"configurable": {"thread_id": "restart-thread"}}
    graph.invoke({
        "messages": [HumanMessage(content="Create a ticket and explain leave policy"),
                     AIMessage(content="Please approve the ticket")],
        "user_name": str(test_user.id), "thread_id": "restart-thread",
        "active_request": "Create a ticket and explain leave policy",
        "requested_routes": ["ticket", "faq"],
    }, config=config)
    connection.close()

    action = pending_action_service.create(
        db_session, test_user.id, "restart-thread", "ticket",
        {"id": "restart-call", "name": "create_ticket", "args": {"content": "VPN"}},
        "Please approve the ticket", 600,
        request_context={"active_request": "Create a ticket and explain leave policy",
                         "requested_routes": ["ticket", "faq"]},
    )
    action.status = "executed"
    action.execution_result = "Ticket TCK-1 created"
    db_session.commit()

    restarted_graph, restarted_connection = _graph(path)
    monkeypatch.setattr(chat_service, "get_app", lambda: restarted_graph)
    continued = chat_service.continue_after_decision(db_session, action)
    assert continued["answer"] == "Ticket TCK-1 created. The leave policy answer is 12 days."
    state = restarted_graph.get_state(config).values
    assert state["route"] == "done"
    assert state["messages"][-2].content == "Ticket TCK-1 created"
    assert state["messages"][-1].content == continued["answer"]
    restarted_connection.close()

    # Simulate a process stopping after checkpoint continuation but before its
    # answer cache commits. The fixed marker prevents duplicate continuation.
    action.decision_answer = None
    db_session.commit()
    graph_again, another_connection = _graph(path)
    monkeypatch.setattr(chat_service, "get_app", lambda: graph_again)
    assert chat_service.continue_after_decision(db_session, action) == continued
    assert len(graph_again.get_state(config).values["messages"]) == len(state["messages"])
    another_connection.close()

    # An ordinary repeat reads the saved answer without touching the graph.
    monkeypatch.setattr(chat_service, "get_app", lambda: 1 / 0)
    assert chat_service.continue_after_decision(db_session, action) == continued


def test_standalone_app_exposes_chat_and_health(
    db_session, test_user, auth_headers, monkeypatch,
):
    def override_db():
        yield db_session

    orchestrator_app.app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(orchestrator_app, "get_app", lambda: object())
    monkeypatch.setattr(orchestrator_app, "get_knowledge_adapter", lambda: object())
    monkeypatch.setattr(routes.chat_service, "send_message", lambda db, user, thread, message: {
        "answer": "Hello", "route": "it_support", "thread_id": thread,
    })
    try:
        with TestClient(orchestrator_app.app) as client:
            assert client.get("/health").json() == {"status": "ok"}
            response = client.post("/v1/chat/messages", json={
                "message": "hello", "thread_id": "standalone-thread",
            }, headers=auth_headers)
            assert response.status_code == 200
            assert response.json()["answer"] == "Hello"
            assert response.json()["thread_id"] == "standalone-thread"
    finally:
        orchestrator_app.app.dependency_overrides.clear()


def test_versioned_chat_rejects_another_owner_of_the_same_thread(
    db_session, test_user, test_user_2, monkeypatch,
):
    class FakeGraph:
        def invoke(self, *_args, **_kwargs):
            return {"messages": [AIMessage(content="Hello")], "route": "it_support"}

    monkeypatch.setattr(chat_service, "get_app", lambda: FakeGraph())
    monkeypatch.setattr(chat_service, "build_memory_context", lambda *_: "")
    first = AuthClaims(subject_id=test_user.id)
    second = AuthClaims(subject_id=test_user_2.id)
    chat_service.send_message(db_session, first, "owner-thread", "hello")
    with pytest.raises(ForbiddenException):
        chat_service.send_message(db_session, second, "owner-thread", "hello")
