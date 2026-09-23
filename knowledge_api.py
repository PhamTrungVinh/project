"""Internal-only knowledge-rag HTTP service."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException

from services.knowledge_service import LocalKnowledgeAdapter
from shared_platform.api_contracts import KnowledgeQueryRequest, KnowledgeQueryResponse

_adapter = LocalKnowledgeAdapter()
_ready = False


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _ready
    _adapter.preload()  # explicit startup work; never on the query path
    _ready = True
    yield
    _ready = False


app = FastAPI(title="Knowledge RAG", version="1.0.0", lifespan=lifespan)


def _authorize(token: str | None) -> None:
    expected = os.getenv("KNOWLEDGE_SERVICE_TOKEN")
    if not expected or token != expected:
        raise HTTPException(status_code=401, detail="Invalid internal service credentials")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    if not _ready:
        raise HTTPException(status_code=503, detail="Knowledge artifacts are not ready")
    return {"status": "ready"}


@app.post("/v1/query", response_model=KnowledgeQueryResponse)
def query(data: KnowledgeQueryRequest, x_internal_service_token: str | None = Header(default=None)):
    _authorize(x_internal_service_token)
    return _adapter.query(data)
