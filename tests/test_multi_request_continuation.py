from langchain_core.messages import AIMessage, HumanMessage

from agents.supervisor import SupervisorDecision, supervisor_node
from agents.rag_agent import rag_agent_node


class _SupervisorLlm:
    def __init__(self, result):
        self.result = result
        self.prompt = ""

    def with_structured_output(self, *_args, **_kwargs):
        return self

    def invoke(self, prompt):
        self.prompt = prompt
        return self.result


def test_supervisor_keeps_original_request_after_confirmation(monkeypatch):
    llm = _SupervisorLlm(
        SupervisorDecision(is_done=False, next_route="faq", final_answer=None)
    )
    monkeypatch.setattr("agents.supervisor.get_chat_llm", lambda: llm)
    state = {
        "active_request": "Create a ticket and tell me the annual leave policy.",
        "messages": [
            HumanMessage(content="Create a ticket and tell me the annual leave policy."),
            HumanMessage(content="ok"),
            AIMessage(content="Created ticket TCK-123."),
        ],
    }

    result = supervisor_node(state)

    assert result["route"] == "faq"
    assert "Create a ticket and tell me the annual leave policy." in llm.prompt
    assert "User's original request: ok" not in llm.prompt


def test_rag_uses_original_request_after_confirmation(monkeypatch):
    received = {}
    monkeypatch.setattr(
        "agents.rag_agent.answer_policy_question",
        lambda query, **_: received.setdefault("query", query) or "policy answer",
    )
    state = {
        "active_request": "Create a ticket and tell me the annual leave policy.",
        "messages": [
            HumanMessage(content="Create a ticket and tell me the annual leave policy."),
            HumanMessage(content="ok"),
        ],
    }

    rag_agent_node(state)

    assert received["query"] == "Create a ticket and tell me the annual leave policy."


def test_supervisor_can_return_to_the_same_agent_for_an_unfinished_action(monkeypatch):
    llm = _SupervisorLlm(
        SupervisorDecision(is_done=False, next_route="ticket", final_answer=None)
    )
    monkeypatch.setattr("agents.supervisor.get_chat_llm", lambda: llm)
    state = {
        "active_request": "Create a ticket and track ticket TCK-801F1A73.",
        "messages": [
            HumanMessage(content="Create a ticket and track ticket TCK-801F1A73."),
            HumanMessage(content="ok"),
            AIMessage(content="Created ticket TCK-NEW."),
        ],
    }

    result = supervisor_node(state)

    assert result["route"] == "ticket"
    assert "MAY require the SAME agent" in llm.prompt
    assert "does not satisfy a request to track" in llm.prompt


def test_supervisor_continues_booking_after_natural_language_ticket_result(monkeypatch):
    llm = _SupervisorLlm(
        SupervisorDecision(is_done=False, next_route="booking")
    )
    monkeypatch.setattr("agents.supervisor.get_chat_llm", lambda: llm)
    state = {
        "active_request": "Make a booking and track ticket TCK-801F1A73.",
        "requested_routes": ["ticket", "booking"],
        "route": "ticket",
        "messages": [
            HumanMessage(content="Make a booking and track ticket TCK-801F1A73."),
            AIMessage(content="Here's the current status of ticket TCK-801F1A73: Pending."),
        ],
    }

    result = supervisor_node(state)

    assert result["route"] == "booking"
    assert result["hop_count"] == 1


def test_supervisor_accepts_completed_named_ticket_tracking(monkeypatch):
    llm = _SupervisorLlm(
        SupervisorDecision(is_done=True, final_answer="Combined results")
    )
    monkeypatch.setattr("agents.supervisor.get_chat_llm", lambda: llm)
    state = {
        "active_request": "Create a ticket and track ticket TCK-801F1A73.",
        "messages": [
            HumanMessage(content="Create a ticket and track ticket TCK-801F1A73."),
            AIMessage(content="ticket_code: TCK-801F1A73\nstatus: Pending"),
        ],
    }

    result = supervisor_node(state)

    assert result["route"] == "done"
    assert result["active_request"] is None


def test_supervisor_continues_an_it_request_after_confirmed_ticket_update(monkeypatch):
    llm = _SupervisorLlm(
        SupervisorDecision(is_done=False, next_route="it_support")
    )
    monkeypatch.setattr("agents.supervisor.get_chat_llm", lambda: llm)
    state = {
        "active_request": "How do I connect Wi-Fi on a phone and update ticket TCK-801F1A73?",
        "requested_routes": ["ticket", "it_support"],
        "completed_routes": [],
        "last_completed_agent": "ticket",
        "route": "confirmed",
        "messages": [
            HumanMessage(content="How do I connect Wi-Fi on a phone and update ticket TCK-801F1A73?"),
            HumanMessage(content="ok"),
            AIMessage(content="Updated ticket TCK-801F1A73."),
        ],
    }

    result = supervisor_node(state)

    assert result["route"] == "it_support"
    assert "Current capability: ticket" in llm.prompt


def test_router_uses_model_plan_for_informal_booking_request(monkeypatch):
    from contextlib import nullcontext
    from agents.router import RouteDecision, router_node

    llm = _SupervisorLlm(RouteDecision(route="ticket", requested_routes=["ticket", "booking"]))
    monkeypatch.setattr("agents.router.get_chat_llm", lambda: llm)
    monkeypatch.setattr("agents.router.get_db_session", lambda: nullcontext(None))
    monkeypatch.setattr("agents.router.pending_action_service.active_tasks", lambda *_: [])
    query = "i want to make a booking and track ticket TCK-5CDFD957"
    result = router_node({"user_name": "1", "messages": [HumanMessage(content=query)]})

    assert result["requested_routes"] == ["ticket", "booking"]
    assert result["active_request"] == query
    assert query in llm.prompt


def test_supervisor_preserves_results_when_waiting_for_booking_details(monkeypatch):
    llm = _SupervisorLlm(SupervisorDecision(
        is_done=True, is_waiting_for_user=True, next_route="booking",
        final_answer="Your ticket is pending. What date and room would you like?",
    ))
    monkeypatch.setattr("agents.supervisor.get_chat_llm", lambda: llm)
    result = supervisor_node({
        "active_request": "Make a booking and track my ticket",
        "route": "booking", "requested_routes": ["booking", "ticket"],
        "agent_responses": ["Your ticket is pending."],
        "messages": [AIMessage(content="What date and room would you like?")],
    })
    assert result["route"] == "done"
    assert result["unfinished_tasks"][0]["agent"] == "booking"
    assert "Your ticket is pending." in result["agent_responses"]
    assert "active_request" not in result


def test_supervisor_hop_limit_preserves_unfinished_request():
    result = supervisor_node({
        "active_request": "Make a booking and track my ticket", "route": "ticket",
        "hop_count": 5, "messages": [AIMessage(content="Your ticket is pending.")],
    })
    assert "couldn't finish all parts" in result["messages"][0].content
    assert "active_request" not in result
    assert result["unfinished_tasks"]


def test_confirmed_booking_result_supersedes_old_question(monkeypatch):
    query = "Make a booking and track ticket TCK-5CDFD957"
    question = "What reason and time would you like for the booking?"
    details = "reason:poosadpasd, time: 8 a.m tomorrow"
    execution_result = "Booking created successfully. booking_code: BKG-47AF58B7"
    llm = _SupervisorLlm(SupervisorDecision(
        is_done=True, final_answer="Booked BKG-47AF58B7. Your ticket is pending."
    ))
    monkeypatch.setattr("agents.supervisor.get_chat_llm", lambda: llm)
    result = supervisor_node({
        "active_request": query, "route": "confirmed", "last_completed_agent": "booking",
        "requested_routes": ["ticket", "booking"], "unfinished_tasks": [],
        "agent_responses": ["Ticket TCK-5CDFD957 is pending.", question],
        "messages": [
            HumanMessage(content="An unrelated older request"),
            HumanMessage(content=query), AIMessage(content=question),
            HumanMessage(content=details), AIMessage(content="Please confirm book_room."),
            HumanMessage(content="ok"), AIMessage(content=execution_result),
        ],
    })
    assert details in llm.prompt
    assert "An unrelated older request" not in llm.prompt
    assert f"Latest result from the current capability:\n{execution_result}" in llm.prompt
    assert "Latest result source: confirmation execution or cancellation result" in llm.prompt
    assert llm.prompt.index(question) < llm.prompt.index(execution_result)
    assert result["route"] == "done"
    assert result["active_request"] is None
    assert not result.get("unfinished_tasks")
    assert "BKG-47AF58B7" in result["messages"][0].content


def test_supervisor_distinguishes_delivered_replies_from_current_turn_results(monkeypatch):
    query = "Make a booking and track my ticket"
    ticket_result = "Ticket TCK-123 is pending."
    displayed = ticket_result + " What time would you like the booking?"
    confirmation = "Please confirm the booking for Monday at 19:00."
    booking_result = "Created booking BKG-456 for Monday at 19:00."
    llm = _SupervisorLlm(SupervisorDecision(is_done=True, final_answer=booking_result))
    monkeypatch.setattr("agents.supervisor.get_chat_llm", lambda: llm)
    supervisor_node({
        "active_request": query, "route": "confirmed", "last_completed_agent": "booking",
        "agent_responses": [ticket_result],
        "messages": [
            HumanMessage(content=query), AIMessage(content=ticket_result),
            AIMessage(content=displayed), HumanMessage(content="Monday at 19:00"),
            AIMessage(content=confirmation), HumanMessage(content="ok"),
            AIMessage(content=booking_result),
        ],
    })
    delivered = llm.prompt.split("Replies already shown to the user in earlier turns of this request:\n")[1].split(
        "\nLatest result from the current capability:"
    )[0]
    assert displayed in delivered
    assert confirmation in delivered
    assert delivered.count(ticket_result) == 1
    assert booking_result not in delivered

    # A ticket result from another agent in the same turn must still be reported.
    supervisor_node({
        "active_request": query, "route": "booking",
        "agent_responses": [ticket_result],
        "messages": [HumanMessage(content=query), AIMessage(content=ticket_result),
                     AIMessage(content="What time would you like the booking?")],
    })
    assert "Replies already shown to the user in earlier turns of this request:\nNone yet." in llm.prompt
    assert ticket_result in llm.prompt


def test_ticket_details_survive_summary_omission_and_are_not_repeated_after_confirmation(monkeypatch):
    query = "Make a booking and track ticket TCK-123"
    ticket = "Ticket TCK-123\nContent: broken phone\nDescription: won't start\nStatus: Pending"
    question = "What reason and time would you like for the booking?"
    llm = _SupervisorLlm(SupervisorDecision(
        is_done=True, is_waiting_for_user=True, next_route="booking",
        final_answer=question,  # Reproduce the model omitting the ticket result.
    ))
    monkeypatch.setattr("agents.supervisor.get_chat_llm", lambda: llm)
    messages = [HumanMessage(content=query), AIMessage(content=ticket), AIMessage(content=question)]
    state = {"active_request": query, "route": "booking", "messages": messages,
             "agent_responses": [ticket]}
    waiting = supervisor_node(state)
    assert waiting["messages"][0].content == ticket + "\n\n" + question
    assert waiting["unfinished_tasks"][0]["question"] == question

    booking = "Booking BKG-456 created. Time: 2026-09-25 13:00. Status: Scheduled."
    llm.result = SupervisorDecision(is_done=True, final_answer=booking + "\n" + ticket)
    finished = supervisor_node({
        **state, **waiting, "route": "confirmed", "last_completed_agent": "booking",
        "unfinished_tasks": [],
        "messages": messages + waiting["messages"] + [
            HumanMessage(content="reason: meeting, time: Friday at 13:00"),
            AIMessage(content="Please confirm the booking."), HumanMessage(content="ok"),
            AIMessage(content=booking),
        ],
    })
    assert finished["messages"][0].content == booking
    assert "TCK-123" not in finished["messages"][0].content
