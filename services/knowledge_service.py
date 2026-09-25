"""Knowledge adapter with local and remote implementations."""

from functools import lru_cache
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import KNOWLEDGE_ADAPTER, KNOWLEDGE_SERVICE_TOKEN, KNOWLEDGE_SERVICE_URL, RAG_ARTIFACT_VERSION
from rag import build_rag_resources, hybrid_retrieve, hyde_query, mmr_select, rerank
from services.ai_adapter import get_embeddings, get_raw_groq_client
from shared_platform.api_contracts import KnowledgePassage, KnowledgeQueryRequest, KnowledgeQueryResponse
from shared_platform.auth_claims import AuthClaims
from logger import agent_logger

RETRIEVAL_VERSION = "v1"
UNAVAILABLE_MESSAGE = "Company-policy information is temporarily unavailable. Please try again later."


def _citations(passages: list[KnowledgePassage]) -> list[str]:
    return list(dict.fromkeys(f"{p.source} (page {p.page})" if p.page else p.source for p in passages))


class LocalKnowledgeAdapter:
    """Local compatibility adapter; preload it before accepting traffic."""

    def preload(self) -> None:
        build_rag_resources()

    def query(self, request: KnowledgeQueryRequest) -> KnowledgeQueryResponse:
        if request.approved_index_version and request.approved_index_version != RAG_ARTIFACT_VERSION:
            return KnowledgeQueryResponse(status="unavailable", retrieval_version=RETRIEVAL_VERSION, index_version=RAG_ARTIFACT_VERSION, reason="requested_index_version_is_not_active")
        try:
            client = get_raw_groq_client()
            embeddings = get_embeddings()
            resources = build_rag_resources()
            docs = hybrid_retrieve(hyde_query(request.query, client), resources["bm25"], resources["dense"], top_n=50)
            docs = rerank(request.query, docs, resources["reranker"], top_k=20)
            docs = mmr_select(request.query, docs, embeddings, top_k=5, lambda_=0.7)
        except Exception:
            return KnowledgeQueryResponse(status="unavailable", retrieval_version=RETRIEVAL_VERSION, index_version=RAG_ARTIFACT_VERSION, reason="retrieval_dependency_unavailable")
        if not docs:
            return KnowledgeQueryResponse(status="unavailable", retrieval_version=RETRIEVAL_VERSION, index_version=RAG_ARTIFACT_VERSION, reason="insufficient_policy_context")
        passages = [KnowledgePassage(content=doc.page_content, source=str(doc.metadata.get("source", "FSoft_HR.pdf")), page=(int(doc.metadata["page"]) + 1 if doc.metadata.get("page") is not None else None), score=1.0 / (rank + 1)) for rank, doc in enumerate(docs)]
        context = "\n\n".join(f"[Source: {p.source}, page {p.page or 'unknown'}]\n{p.content}" for p in passages)
        try:
            completion = client.chat.completions.create(model="openai/gpt-oss-120b", messages=[{"role": "system", "content": "Only answer using the provided company-policy context. Say information is unavailable when context is insufficient."}, {"role": "user", "content": f"Context:\n{context}\n\nQuestion:\n{request.query}"}])
        except Exception:
            return KnowledgeQueryResponse(status="degraded", passages=passages, citations=_citations(passages), retrieval_version=RETRIEVAL_VERSION, index_version=RAG_ARTIFACT_VERSION, reason="answer_generation_unavailable")
        return KnowledgeQueryResponse(status="ok", answer=completion.choices[0].message.content, passages=passages, citations=_citations(passages), retrieval_version=RETRIEVAL_VERSION, index_version=RAG_ARTIFACT_VERSION)


class HttpKnowledgeAdapter:
    def query(self, request: KnowledgeQueryRequest) -> KnowledgeQueryResponse:
        headers = {"Content-Type": "application/json", "X-Correlation-ID": request.correlation_id}
        if KNOWLEDGE_SERVICE_TOKEN:
            headers["X-Internal-Service-Token"] = KNOWLEDGE_SERVICE_TOKEN
        started = time.monotonic()
        status_code = None
        error_type = None
        try:
            with urlopen(Request(f"{KNOWLEDGE_SERVICE_URL.rstrip('/')}/v1/query", data=request.model_dump_json().encode(), headers=headers, method="POST"), timeout=5) as response:
                status_code = response.status
                return KnowledgeQueryResponse.model_validate_json(response.read())
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            status_code = exc.code if isinstance(exc, HTTPError) else status_code
            error_type = type(exc).__name__
            return KnowledgeQueryResponse(status="unavailable", retrieval_version=RETRIEVAL_VERSION, reason="knowledge_service_unavailable")
        finally:
            agent_logger.info(
                "service_call target=knowledge-rag method=POST status=%s duration_ms=%s result=%s",
                status_code, round((time.monotonic() - started) * 1000),
                "error" if error_type else "ok",
            )


@lru_cache(maxsize=1)
def get_knowledge_adapter():
    return HttpKnowledgeAdapter() if KNOWLEDGE_ADAPTER == "http" else LocalKnowledgeAdapter()


def query_policy(query: str, requester: AuthClaims, correlation_id: str, approved_index_version: str | None = None) -> KnowledgeQueryResponse:
    return get_knowledge_adapter().query(KnowledgeQueryRequest(query=query, requester=requester, correlation_id=correlation_id, approved_index_version=approved_index_version))


def answer_policy_question(query: str, owner_id: int = 0, correlation_id: str = "local") -> str:
    """Compatibility wrapper for the existing graph node."""
    result = query_policy(query, AuthClaims(subject_id=owner_id), correlation_id)
    return result.answer if result.status == "ok" and result.answer else UNAVAILABLE_MESSAGE
