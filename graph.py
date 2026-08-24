from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from config import HITL_ENABLED
from memory import trim_working_memory, search_facts, search_episodes, save_fact, save_episode
from agents.supervisor import supervisor_node, supervisor_decision

from state import AgentState
from context import context_node
from agents import (
    router_node,
    route_decision,
    web_agent_node,
    should_continue,
    tool_node,
    rag_agent_node,
    ticket_agent_node,
    ticket_should_continue,
    ticket_tool_node,
    booking_agent_node,
    booking_should_continue,
    booking_tool_node,
    it_support_agent_node,
    it_support_should_continue,
    it_tool_node,
)
from guardrail import guardrail_node, guardrail_decision, blocked_response_node
from logger import agent_logger


def load_memory_node(state: AgentState) -> dict:
    """
    Runs after the guardrail and before the context node.
    Loads relevant Semantic and Episodic memory into the state
    so that child agents can use it as context.
    """
    user_id = state.get("user_name", "anonymous")
    query = state["messages"][-1].content

    facts = search_facts(user_id, query)
    episodes = search_episodes(user_id, query)

    agent_logger.info(f"LOAD_MEMORY found facts={len(facts)} episodes={len(episodes)}")

    parts = []
    if facts:
        parts.append(
            "Known facts about this user:\n"
            + "\n".join(f"- {f}" for f in facts)
        )

    if episodes:
        parts.append(
            "Relevant past interactions:\n"
            + "\n".join(
                f"- {e['summary']} -> {e['outcome']}" for e in episodes
            )
        )

    result = "\n\n".join(parts)
    if result:
        agent_logger.info(f"LOAD_MEMORY injected context:\n{result}")

    return {"retrieved_memory": "\n\n".join(parts)}


def trim_memory_node(state: AgentState) -> dict:
    """
    Working memory: trim the context window before passing it to the router.
    """
    to_remove = trim_working_memory(state["messages"])
    return {"messages": to_remove}

def build_graph():
    workflow = StateGraph(AgentState)

    # ---------- Nodes ----------
    workflow.add_node("context", context_node)
    workflow.add_node("router", router_node)          # Primary Assistant

    workflow.add_node("rag_agent", rag_agent_node)      # FAQ Agent

    workflow.add_node("web_agent", web_agent_node)      # General web/calc
    workflow.add_node("tools", tool_node)

    workflow.add_node("ticket_agent", ticket_agent_node)
    workflow.add_node("ticket_tools", ticket_tool_node)

    workflow.add_node("booking_agent", booking_agent_node)
    workflow.add_node("booking_tools", booking_tool_node)

    workflow.add_node("it_support_agent", it_support_agent_node)
    workflow.add_node("it_tools", it_tool_node)


    workflow.add_node("guardrail", guardrail_node)
    workflow.add_node("blocked", blocked_response_node)

    workflow.add_node("load_memory", load_memory_node)
    workflow.add_node("trim_memory", trim_memory_node)

    workflow.add_node("supervisor", supervisor_node)


    workflow.add_edge(START, "guardrail")

    workflow.add_conditional_edges(
        "guardrail",
        guardrail_decision,
        {
            "blocked": "blocked",
            "allowed": "load_memory",
        },
    )
    workflow.add_edge("blocked", END)
    workflow.add_edge("load_memory", "trim_memory")
    workflow.add_edge("trim_memory", "context")
    workflow.add_edge("context", "router")

    # Primary router node: decides which agent to use based on user input
    workflow.add_conditional_edges(
        "router",
        route_decision,
        {
            "rag_agent": "rag_agent",
            "web_agent": "web_agent",
            "ticket_agent": "ticket_agent",
            "it_support_agent": "it_support_agent",
            "booking_agent": "booking_agent",
        },
    )

    # ---------- FAQ Agent ----------
    workflow.add_edge("rag_agent", "supervisor")

    # ---------- Web Agent (general + calculator) ----------
    workflow.add_conditional_edges(
        "web_agent", should_continue, {"tools": "tools", "end": "supervisor"}
    )
    workflow.add_edge("tools", "web_agent")

    # ---------- Ticket Support Agent ----------
    workflow.add_conditional_edges(
        "ticket_agent",
        ticket_should_continue,
        {"tools": "ticket_tools", "end": "supervisor"},
    )
    workflow.add_edge("ticket_tools", "ticket_agent")

    # ---------- Booking Agent ----------
    workflow.add_conditional_edges(
        "booking_agent",
        booking_should_continue,
        {"tools": "booking_tools", "end": "supervisor"},
    )
    workflow.add_edge("booking_tools", "booking_agent")

    # ---------- IT Support Agent ----------
    workflow.add_conditional_edges(
        "it_support_agent",
        it_support_should_continue,
        {"tools": "it_tools", "end": "supervisor"},
    )
    workflow.add_edge("it_tools", "it_support_agent")

    # ---------- Supervisor ----------
    workflow.add_conditional_edges(
    "supervisor",
    supervisor_decision,
    {
        "rag_agent": "rag_agent",
        "web_agent": "web_agent",
        "ticket_agent": "ticket_agent",
        "it_support_agent": "it_support_agent",
        "booking_agent": "booking_agent",
        "final": END,
    },
)

    conn = sqlite3.connect("checkpoints.db", check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    interrupt_nodes = ["ticket_tools", "booking_tools"] if HITL_ENABLED else []

    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_nodes,
    )
