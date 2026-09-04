import sqlite3
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

from state import AgentState
from context import context_node
from guardrail import guardrail_node, guardrail_decision, blocked_response_node
from agents import (
    router_node, route_decision,
    supervisor_node, supervisor_decision,
    rag_agent_node,
    web_agent_node, should_continue, web_tools_node,
    ticket_agent_node, ticket_should_continue, ticket_tools_node, ticket_confirm_node,
    booking_agent_node, booking_should_continue, booking_tools_node, booking_confirm_node,
    it_support_agent_node, it_support_should_continue, it_tool_node,
)


def _passthrough(state: AgentState) -> dict:
    return {}


def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("guardrail", guardrail_node)
    workflow.add_node("blocked", blocked_response_node)
    workflow.add_node("context", context_node)
    workflow.add_node("router", router_node)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("confirmed", _passthrough)

    workflow.add_node("rag_agent", rag_agent_node)

    workflow.add_node("web_agent", web_agent_node)
    workflow.add_node("web_tools", web_tools_node)

    workflow.add_node("ticket_agent", ticket_agent_node)
    workflow.add_node("ticket_tools", ticket_tools_node)
    workflow.add_node("ticket_confirm", ticket_confirm_node)

    workflow.add_node("booking_agent", booking_agent_node)
    workflow.add_node("booking_tools", booking_tools_node)
    workflow.add_node("booking_confirm", booking_confirm_node)

    workflow.add_node("it_support_agent", it_support_agent_node)
    workflow.add_node("it_tools", it_tool_node)

    workflow.add_edge(START, "guardrail")
    workflow.add_conditional_edges("guardrail", guardrail_decision, {"blocked": "blocked", "allowed": "context"})
    workflow.add_edge("blocked", END)
    workflow.add_edge("context", "router")

    workflow.add_conditional_edges("router", route_decision, {
        "rag_agent": "rag_agent", 
        "web_agent": "web_agent", 
        "ticket_agent": "ticket_agent",
        "it_support_agent": "it_support_agent", 
        "booking_agent": "booking_agent",
        "confirmed": "confirmed",
    })
    workflow.add_edge("confirmed", END)

    workflow.add_edge("rag_agent", "supervisor")

    workflow.add_conditional_edges("web_agent", should_continue, {"tools": "web_tools", "end": "supervisor"})
    workflow.add_edge("web_tools", "web_agent")

    workflow.add_conditional_edges("ticket_agent", ticket_should_continue, {
        "tools": "ticket_tools", "confirm": "ticket_confirm", "end": "supervisor",
    })
    workflow.add_edge("ticket_tools", "ticket_agent")
    workflow.add_edge("ticket_confirm", END)

    workflow.add_conditional_edges("booking_agent", booking_should_continue, {
        "tools": "booking_tools", "confirm": "booking_confirm", "end": "supervisor",
    })
    workflow.add_edge("booking_tools", "booking_agent")
    workflow.add_edge("booking_confirm", END)

    workflow.add_conditional_edges("it_support_agent", it_support_should_continue, {"tools": "it_tools", "end": "supervisor"})
    workflow.add_edge("it_tools", "it_support_agent")

    workflow.add_conditional_edges("supervisor", supervisor_decision, {
        "rag_agent": "rag_agent", "web_agent": "web_agent", "ticket_agent": "ticket_agent",
        "it_support_agent": "it_support_agent", "booking_agent": "booking_agent", "final": END,
    })

    conn = sqlite3.connect("checkpoints.db", check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    return workflow.compile(checkpointer=checkpointer)