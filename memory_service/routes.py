"""Memory API shared by standalone and multi-agent applications."""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from schemas.chat import MemoryClearResponse, MemoryFactCreate, TaskOutcomeRequest
from services import memory_service
from shared_platform.auth_claims import AuthClaims
from shared_platform.claims_dependency import get_current_claims
from shared_platform.domain_persistence import domain_dependency

router = APIRouter(prefix="/v1/memory", tags=["memory"])
get_memory_db = domain_dependency("memory")


@router.post("/facts", status_code=status.HTTP_201_CREATED)
def add_fact(data: MemoryFactCreate, db: Session = Depends(get_memory_db), claims: AuthClaims = Depends(get_current_claims)):
    memory_service.remember_fact(db, claims.subject_id, data.fact)
    return {"status": "success"}


@router.delete("", response_model=MemoryClearResponse)
def clear_memory(db: Session = Depends(get_memory_db), claims: AuthClaims = Depends(get_current_claims)):
    return memory_service.clear_all_memory(db, claims.subject_id)


@router.post("/episodes", status_code=status.HTTP_201_CREATED)
def add_episode(data: TaskOutcomeRequest, db: Session = Depends(get_memory_db), claims: AuthClaims = Depends(get_current_claims)):
    memory_service.remember_episode(db, claims.subject_id, data.thread_id, data.summary, data.outcome)
    return {"status": "success"}


@router.get("/context")
def retrieve_context(query: str, db: Session = Depends(get_memory_db), claims: AuthClaims = Depends(get_current_claims)):
    return {"context": memory_service.build_memory_context(db, claims.subject_id, query)}
