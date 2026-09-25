from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from confirmation import build_confirmation_response, completed_results_for_current_request
from agents import router as router_module
from services import pending_action_service


def test_confirmation_includes_completed_results_from_same_request():
    messages = [
        HumanMessage(content="Track TCK-1 and book a room"),
        AIMessage(content="", tool_calls=[{"name": "track_ticket", "args": {"ticket_code": "TCK-1"}, "id": "call-1"}]),
        ToolMessage(content="ticket_code: TCK-1\nstatus: Pending", tool_call_id="call-1", name="track_ticket"),
        AIMessage(content="", tool_calls=[{"name": "book_room", "args": {"reason": "Planning", "time": "2026-09-14 14:00"}, "id": "call-2"}]),
    ]

    response = build_confirmation_response(
        [{"name": "book_room", "args": {"reason": "Planning", "time": "2026-09-14 14:00"}}],
        completed_results_for_current_request(messages),
    )

    assert "ticket_code: TCK-1" in response
    assert "book_room(reason=Planning, time=2026-09-14 14:00)" in response


def test_confirmation_does_not_repeat_results_from_an_older_request():
    messages = [
        HumanMessage(content="Track TCK-1"),
        ToolMessage(content="ticket_code: TCK-1", tool_call_id="call-1", name="track_ticket"),
        AIMessage(content="Ticket is pending."),
        HumanMessage(content="Book a room"),
        AIMessage(content="", tool_calls=[{"name": "book_room", "args": {}, "id": "call-2"}]),
    ]

    assert completed_results_for_current_request(messages) == []


def test_typed_reply_resolves_pending_action(db_session, test_user, monkeypatch):
    class Matcher:
        def __init__(self, intent, action_id):
            self.intent = intent
            self.action_id = action_id

        def with_structured_output(self, *_args, **_kwargs):
            return self

        def invoke(self, _prompt):
            return router_module.TaskMatch(matches_task_id=self.action_id, intent=self.intent)

    for intent, reply, expected_status in (
        ("confirm", "yes, please", "executed"),
        ("cancel", "cancel", "rejected"),
    ):
        action = pending_action_service.create(
            db_session, test_user.id, f"thread-{intent}", "ticket",
            {"name": "create_ticket", "args": {"content": "VPN", "description": "Down"}},
            "Create a ticket?", 600,
        )
        monkeypatch.setattr(router_module, "get_chat_llm", lambda: Matcher(intent, action.id))
        calls = []
        monkeypatch.setattr(router_module, "execute_confirmed_tool_call",
                            lambda *_args, **_kwargs: calls.append(True) or "Ticket created")
        result = router_module.router_node({
            "messages": [HumanMessage(content=reply)],
            "user_name": str(test_user.id),
            "customer_name": test_user.full_name,
            "user_email": test_user.email,
            "thread_id": f"thread-{intent}",
            "unfinished_tasks": [],
        })
        db_session.refresh(action)
        assert action.status == expected_status
        assert result["route"] == "confirmed"
        assert len(calls) == (1 if intent == "confirm" else 0)
