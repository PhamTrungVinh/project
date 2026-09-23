from shared_platform.api_contracts import KnowledgeQueryRequest, KnowledgeQueryResponse
from shared_platform.auth_claims import AuthClaims
from services import knowledge_service


def _request(**overrides):
    values = {"query": "What is the leave policy?", "requester": AuthClaims(subject_id=7), "correlation_id": "corr-7"}
    values.update(overrides)
    return KnowledgeQueryRequest(**values)


def test_local_knowledge_returns_unavailable_for_wrong_index(monkeypatch):
    monkeypatch.setattr(knowledge_service, "RAG_ARTIFACT_VERSION", "approved-v1")
    response = knowledge_service.LocalKnowledgeAdapter().query(_request(approved_index_version="other-v1"))
    assert response.status == "unavailable"
    assert response.reason == "requested_index_version_is_not_active"
    assert response.index_version == "approved-v1"


def test_http_adapter_returns_safe_unavailable_on_timeout(monkeypatch):
    monkeypatch.setattr(knowledge_service, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()))
    response = knowledge_service.HttpKnowledgeAdapter().query(_request())
    assert response.status == "unavailable"
    assert response.reason == "knowledge_service_unavailable"


def test_knowledge_response_preserves_versioned_contract():
    response = KnowledgeQueryResponse(status="ok", answer="Policy answer", citations=["FSoft_HR.pdf (page 2)"], retrieval_version="v1", index_version="approved-v1")
    assert KnowledgeQueryResponse.model_validate_json(response.model_dump_json()) == response
