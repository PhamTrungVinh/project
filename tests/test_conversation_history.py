from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from crud import conversation as conv_crud
from services import conversation_history_service as history_service
from services import pending_action_service
from chat_orchestrator.pending_action_model import PendingAction


def _save(db, owner_id, thread, title):
    conversation = conv_crud.create_conversation(db, owner_id, thread)
    conv_crud.set_title_if_empty(db, thread, title)
    return conversation


def test_conversation_list_returns_only_owners_titles(client, auth_headers, test_user, test_user_2, db_session):
    _save(db_session, test_user.id, "my-chat", "My first question")
    _save(db_session, test_user_2.id, "private-chat", "Someone else's title")
    response = client.get("/v1/chat/conversations", headers=auth_headers)
    assert response.status_code == 200
    assert [(row["thread_id"], row["title"]) for row in response.json()] == [("my-chat", "My first question")]


def test_history_restores_user_turns_and_final_answers_only(client, auth_headers, test_user, db_session, monkeypatch):
    _save(db_session, test_user.id, "saved-chat", "Track my ticket")
    messages = [
        SystemMessage(content="Private system prompt"),
        HumanMessage(id="user-1", content="Track my ticket"),
        AIMessage(content="Internal agent draft"),
        AIMessage(content="", tool_calls=[{"name": "track_ticket", "args": {"private": "value"}, "id": "tool-call"}]),
        ToolMessage(content="Internal database result", tool_call_id="tool-call"),
        AIMessage(id="answer-1", content="Ticket is pending."),
        HumanMessage(id="user-2", content="Explain leave policy"),
        AIMessage(content="Intermediate policy text"),
        AIMessage(id="answer-2", content="**12 days** of leave."),
    ]
    seen = []

    class Graph:
        def get_state(self, config):
            seen.append(config)
            return SimpleNamespace(values={"messages": messages, "route": "done"})

    monkeypatch.setattr(history_service, "get_app", lambda: Graph())
    response = client.get("/v1/chat/conversations/saved-chat/messages", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Track my ticket"
    assert body["history_available"] is True
    assert body["messages"] == [
        {"id": "user-1", "role": "user", "text": "Track my ticket"},
        {"id": "answer-1", "role": "assistant", "text": "Ticket is pending."},
        {"id": "user-2", "role": "user", "text": "Explain leave policy"},
        {"id": "answer-2", "role": "assistant", "text": "**12 days** of leave."},
    ]
    assert seen == [{"configurable": {"thread_id": "saved-chat"}}]


def test_history_checks_ownership_before_loading_checkpoint(client, auth_headers_user_2, test_user, db_session, monkeypatch):
    _save(db_session, test_user.id, "private-chat", "Private")
    monkeypatch.setattr(history_service, "get_app", lambda: 1 / 0)
    assert client.get("/v1/chat/conversations/private-chat/messages", headers=auth_headers_user_2).status_code == 403
    assert client.get("/v1/chat/conversations/missing/messages", headers=auth_headers_user_2).status_code == 404
    assert client.get("/v1/chat/conversations/private-chat/messages").status_code == 401


def test_missing_checkpoint_retains_saved_conversation_metadata(client, auth_headers, test_user, db_session, monkeypatch):
    _save(db_session, test_user.id, "old-chat", "Old question")
    monkeypatch.setattr(history_service, "get_app", lambda: SimpleNamespace(get_state=lambda _: SimpleNamespace(values={})))
    response = client.get("/v1/chat/conversations/old-chat/messages", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["title"] == "Old question"
    assert response.json()["messages"] == []
    assert response.json()["history_available"] is False


def test_continuing_saved_thread_keeps_original_title_and_messages(client, auth_headers, test_user, db_session, monkeypatch, tmp_path):
    import sqlite3
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.graph import START, END, StateGraph
    from services import chat_service
    from state import AgentState

    connection = sqlite3.connect(str(tmp_path / "history.db"), check_same_thread=False)
    workflow = StateGraph(AgentState)
    workflow.add_node("reply", lambda state: {"messages": [AIMessage(content="Reply: " + state["messages"][-1].content)]})
    workflow.add_edge(START, "reply")
    workflow.add_edge("reply", END)
    graph = workflow.compile(checkpointer=SqliteSaver(connection))
    monkeypatch.setattr(chat_service, "get_app", lambda: graph)
    monkeypatch.setattr(history_service, "get_app", lambda: graph)
    monkeypatch.setattr(chat_service, "_load_memory_context", lambda *args: "")
    try:
        for message in ["First question", "Follow-up"]:
            response = client.post("/v1/chat/messages", json={"thread_id": "continue-chat", "message": message}, headers=auth_headers)
            assert response.status_code == 200
        response = client.get("/v1/chat/conversations/continue-chat/messages", headers=auth_headers)
        assert response.json()["title"] == "First question"
        assert [item["text"] for item in response.json()["messages"]] == [
            "First question", "Reply: First question", "Follow-up", "Reply: Follow-up"]
    finally:
        connection.close()


def test_delete_chat_removes_checkpoint_and_approvals_without_touching_other_chat(
    client, auth_headers, test_user, db_session, monkeypatch, tmp_path,
):
    import sqlite3
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.graph import START, END, StateGraph
    from state import AgentState

    connection = sqlite3.connect(str(tmp_path / "delete.db"), check_same_thread=False)
    workflow = StateGraph(AgentState)
    workflow.add_node("reply", lambda _: {"messages": [AIMessage(content="Saved answer")]})
    workflow.add_edge(START, "reply")
    workflow.add_edge("reply", END)
    graph = workflow.compile(checkpointer=SqliteSaver(connection))
    monkeypatch.setattr(history_service, "get_app", lambda: graph)
    try:
        for thread in ["delete-me", "keep-me"]:
            _save(db_session, test_user.id, thread, thread)
            graph.invoke({"messages": [HumanMessage(content=thread)]}, {"configurable": {"thread_id": thread}})
            pending_action_service.create(db_session, test_user.id, thread, "ticket",
                {"name": "create_ticket", "args": {"content": "VPN"}, "id": thread}, "Create ticket?", 600)

        response = client.delete("/v1/chat/conversations/delete-me", headers=auth_headers)
        assert response.status_code == 204
        assert response.content == b""
        assert conv_crud.get_conversation(db_session, "delete-me") is None
        assert db_session.query(PendingAction).filter_by(thread_id="delete-me").count() == 0
        assert list(graph.checkpointer.list({"configurable": {"thread_id": "delete-me"}})) == []
        for table in ["checkpoints", "writes"]:
            assert connection.execute(f"SELECT COUNT(*) FROM {table} WHERE thread_id = ?", ("delete-me",)).fetchone()[0] == 0
        assert graph.get_state({"configurable": {"thread_id": "keep-me"}}).values["messages"]
        assert conv_crud.get_conversation(db_session, "keep-me") is not None
        assert db_session.query(PendingAction).filter_by(thread_id="keep-me").count() == 1
        assert client.get("/v1/chat/conversations/delete-me/messages", headers=auth_headers).status_code == 404
        assert [row["thread_id"] for row in client.get("/v1/chat/conversations", headers=auth_headers).json()] == ["keep-me"]
    finally:
        connection.close()


def test_delete_rejects_other_users_and_missing_chats(client, auth_headers_user_2, test_user, db_session, monkeypatch):
    _save(db_session, test_user.id, "private-delete", "Private chat")
    monkeypatch.setattr(history_service, "get_app", lambda: 1 / 0)
    assert client.delete("/v1/chat/conversations/private-delete", headers=auth_headers_user_2).status_code == 403
    assert client.delete("/v1/chat/conversations/missing", headers=auth_headers_user_2).status_code == 404
    assert client.delete("/v1/chat/conversations/private-delete").status_code == 401
    assert conv_crud.get_conversation(db_session, "private-delete") is not None


def test_checkpoint_cleanup_failure_keeps_chat_and_approvals_for_retry(client, auth_headers, test_user, db_session, monkeypatch):
    _save(db_session, test_user.id, "retry-delete", "Retry chat")
    pending_action_service.create(db_session, test_user.id, "retry-delete", "ticket",
        {"name": "create_ticket", "args": {}, "id": "retry-delete"}, "Create?", 600)

    def fail(_):
        raise RuntimeError("private database error")

    monkeypatch.setattr(history_service, "get_app", lambda: SimpleNamespace(checkpointer=SimpleNamespace(delete_thread=fail)))
    response = client.delete("/v1/chat/conversations/retry-delete", headers=auth_headers)
    assert response.status_code == 503
    assert "private database error" not in response.text
    assert conv_crud.get_conversation(db_session, "retry-delete") is not None
    assert db_session.query(PendingAction).filter_by(thread_id="retry-delete").count() == 1
    monkeypatch.setattr(history_service, "get_app", lambda: SimpleNamespace(checkpointer=SimpleNamespace(delete_thread=lambda _: None)))
    assert client.delete("/v1/chat/conversations/retry-delete", headers=auth_headers).status_code == 204
