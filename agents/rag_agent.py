from langchain_core.messages import HumanMessage, AIMessage

from services.knowledge_service import answer_policy_question
from state import AgentState
from rag import build_rag_resources, mmr_select, rerank, hybrid_retrieve, hyde_query
from logger import agent_logger
from shared_platform.observability import correlation_id

RAG_SYSTEM_PROMPT = (
    "Only answer using the provided context. "
    "Say \"I don't have information about this\" when context is insufficient. "
    "Cite the source document when possible."
)


def rag_agent_node(state: AgentState) -> dict:
    # On a confirmation turn the latest user text may only be "ok".
    # Query the parent request so policy work from a multi-request turn survives.
    query = state.get("active_request") or next(
        (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), ""
    )

    agent_logger.info("rag_retrieval_started")
    answer = answer_policy_question(query, owner_id=int(state.get("user_name") or 0), correlation_id=correlation_id() or "chat-turn")

    return {"messages": [AIMessage(content=answer)]}