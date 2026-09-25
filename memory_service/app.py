"""Standalone local entry point for the memory domain service."""

from fastapi import Depends, FastAPI, status
from sqlalchemy.orm import Session

from database import get_db
from shared_platform.claims_dependency import get_current_claims
from shared_platform.auth_claims import AuthClaims
from schemas.chat import MemoryClearResponse, MemoryFactCreate, TaskOutcomeRequest
from services import memory_service
from shared_platform.request_context import request_context_middleware

app = FastAPI(title="Memory Service", version="v1")
app.middleware("http")(request_context_middleware)



@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    return {"status": "ready"}


@app.post("/v1/memory/facts", status_code=status.HTTP_201_CREATED)
def add_fact(data: MemoryFactCreate, db: Session = Depends(get_db), claims: AuthClaims = Depends(get_current_claims)):
    memory_service.remember_fact(db, claims.subject_id, data.fact)
    return {"status": "success"}


@app.delete("/v1/memory", response_model=MemoryClearResponse)
def clear_memory(db: Session = Depends(get_db), claims: AuthClaims = Depends(get_current_claims)):
    return memory_service.clear_all_memory(db, claims.subject_id)

@app.post("/v1/memory/episodes", status_code=status.HTTP_201_CREATED)
def add_episode(data: TaskOutcomeRequest, db: Session = Depends(get_db), claims: AuthClaims = Depends(get_current_claims)):
    memory_service.remember_episode(db, claims.subject_id, data.thread_id, data.summary, data.outcome)
    return {"status": "success"}



@app.get("/v1/memory/context")
def retrieve_context(query: str, db: Session = Depends(get_db), claims: AuthClaims = Depends(get_current_claims)):
    return {"context": memory_service.build_memory_context(db, claims.subject_id, query)}

from shared_platform.domain_persistence import domain_dependency

app.dependency_overrides[get_db] = domain_dependency("memory")
