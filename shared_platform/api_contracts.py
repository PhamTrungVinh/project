from typing import Literal

from pydantic import BaseModel, Field

from shared_platform.auth_claims import AuthClaims


class ErrorResponse(BaseModel):
    detail: str


class KnowledgeQueryRequest(BaseModel):
    """Versioned internal contract for approved-policy retrieval."""

    query: str = Field(min_length=1, max_length=8_000)
    requester: AuthClaims
    correlation_id: str = Field(min_length=1, max_length=255)
    approved_index_version: str | None = Field(default=None, max_length=255)


class KnowledgePassage(BaseModel):
    content: str
    source: str
    page: int | None = None
    score: float


class KnowledgeQueryResponse(BaseModel):
    status: Literal["ok", "unavailable", "degraded"]
    answer: str | None = None
    passages: list[KnowledgePassage] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    retrieval_version: str | None = None
    index_version: str | None = None
    reason: str | None = None
