from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from confirmation import build_confirmation_response, completed_results_for_current_request


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
