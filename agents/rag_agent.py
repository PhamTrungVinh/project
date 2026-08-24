from langchain.messages import AIMessage

from config import groq_client, embeddings
from state import AgentState
from rag import build_rag_resources, mmr_select, rerank, hybrid_retrieve, hyde_query
from logger import agent_logger

RAG_SYSTEM_PROMPT = (
    "Only answer using the provided context. "
    "Say \"I don't have information about this\" when context is insufficient. "
    "Cite the source document when possible."
)


def rag_agent_node(state: AgentState) -> dict:
    query = state["messages"][-1].content
    user_email = state.get("user_email")  # lấy từ context, có thể None

    resources = build_rag_resources()  # lazy, cached sau lần đầu
    bm25, dense, reranker = resources["bm25"], resources["dense"], resources["reranker"]

    hyde = hyde_query(query, groq_client)
    docs = hybrid_retrieve(hyde, bm25, dense, top_n=50)
    docs = rerank(query, docs, reranker, top_k=20)
    docs = mmr_select(query, docs, embeddings, top_k=5, lambda_=0.7)

    context = "\n\n".join(
        f"[Page {doc.metadata['page'] + 1}]\n{doc.page_content}" for doc in docs
    )

    completion = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": RAG_SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion:\n{query}"},
        ],
    )

    answer = completion.choices[0].message.content

    if user_email:
        print(f"[RAG audit] user={user_email} query={query!r}")

    agent_logger.info(
        f"RAG_AGENT query={query!r} -> answer={answer[:200]!r} context_length={len(context)}"
    )
    return {"messages": [AIMessage(content=answer)], "context": context}
