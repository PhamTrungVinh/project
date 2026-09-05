from langchain_core.messages import HumanMessage, AIMessage

from services.ai_adapter import get_raw_groq_client, get_embeddings
from state import AgentState
from rag import build_rag_resources, mmr_select, rerank, hybrid_retrieve, hyde_query
from logger import agent_logger

RAG_SYSTEM_PROMPT = (
    "Only answer using the provided context. "
    "Say \"I don't have information about this\" when context is insufficient. "
    "Cite the source document when possible."
)


def rag_agent_node(state: AgentState) -> dict:
    query = next((m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)), "")

    agent_logger.info("rag_retrieval_started")
    groq_client = get_raw_groq_client()
    embeddings = get_embeddings()
    resources = build_rag_resources()
    bm25, dense, reranker = resources["bm25"], resources["dense"], resources["reranker"]

    hyde = hyde_query(query, groq_client)
    docs = hybrid_retrieve(hyde, bm25, dense, top_n=50)
    docs = rerank(query, docs, reranker, top_k=20)
    docs = mmr_select(query, docs, embeddings, top_k=5, lambda_=0.7)

    context = "\n\n".join(f"[Page {doc.metadata['page'] + 1}]\n{doc.page_content}" for doc in docs)

    completion = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion:\n{query}"},
        ],
    )
    answer = completion.choices[0].message.content

    agent_logger.info("rag_retrieval_completed selected_documents=%s", len(docs))
    return {"messages": [AIMessage(content=answer)]}