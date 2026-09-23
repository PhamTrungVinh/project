import sqlite3

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

from config import get_checkpoint_database_url
from state import AgentState
from context import context_node
from guardrail import guardrail_node, guardrail_decision, blocked_response_node
from agents import (
    router_node, route_decision,
    supervisor_node, supervisor_decision,
    rag_agent_node,
    ticket_agent_node, ticket_should_continue, ticket_tools_node, ticket_confirm_node,
    booking_agent_node, booking_should_continue, booking_tools_node, booking_confirm_node,
    it_support_agent_node, it_support_should_continue, it_tool_node,
)

_postgres_checkpointer_context = None


def _passthrough(state: AgentState) -> dict:
    return {}


def build_checkpointer():
    """Use a shared PostgreSQL saver when configured, otherwise local SQLite."""
    global _postgres_checkpointer_context
    checkpoint_url = get_checkpoint_database_url()
    if checkpoint_url is None:
        connection = sqlite3.connect("checkpoints.db", check_same_thread=False)
        return SqliteSaver(connection)

    from langgraph.checkpoint.postgres import PostgresSaver

    _postgres_checkpointer_context = PostgresSaver.from_conn_string(checkpoint_url)
    saver = _postgres_checkpointer_context.__enter__()
    saver.setup()
    return saver


def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("guardrail", guardrail_node)
    workflow.add_node("blocked", blocked_response_node)
    workflow.add_node("context", context_node)
    workflow.add_node("router", router_node)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("confirmed", _passthrough)
    workflow.add_node("rag_agent", rag_agent_node)
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
        "rag_agent": "rag_agent", "ticket_agent": "ticket_agent",
        "booking_agent": "booking_agent", "it_support_agent": "it_support_agent",
        "confirmed": "confirmed",
    })
    workflow.add_edge("confirmed", "supervisor")
    workflow.add_edge("rag_agent", "supervisor")
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
    workflow.add_conditional_edges("it_support_agent", it_support_should_continue, {
        "tools": "it_tools", "end": "supervisor", "final": END,
    })
    workflow.add_edge("it_tools", "it_support_agent")
    workflow.add_conditional_edges("supervisor", supervisor_decision, {
        "rag_agent": "rag_agent", "ticket_agent": "ticket_agent",
        "booking_agent": "booking_agent", "it_support_agent": "it_support_agent", "final": END,
    })
    return workflow.compile(checkpointer=build_checkpointer())
