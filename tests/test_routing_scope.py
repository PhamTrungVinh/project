from agents.router import ROUTER_PROMPT, route_decision


def test_only_existing_agent_routes_are_returned():
    assert route_decision({"route": "faq"}) == "rag_agent"
    assert route_decision({"route": "ticket"}) == "ticket_agent"
    assert route_decision({"route": "booking"}) == "booking_agent"
    assert route_decision({"route": "it_support"}) == "it_support_agent"


def test_unknown_routes_fall_back_to_existing_llm_agent():
    assert route_decision({"route": "web"}) == "it_support_agent"


def test_router_prompt_prioritizes_ticket_actions_over_faq():
    assert '"I need to create a ticket" -> ticket' in ROUTER_PROMPT
    assert "Do not send ticket or booking\nrequests to FAQ" in ROUTER_PROMPT
    assert "This rule takes priority" in ROUTER_PROMPT
