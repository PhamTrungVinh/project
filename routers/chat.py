import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models.user import User
from schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationOut,
    TaskOutcomeRequest,
    MemoryFactCreate,
    MemoryClearResponse,
)
from services import chat_service, memory_service
from crud import conversation as conv_crud

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/", response_model=ChatResponse)
def chat_message(
    data: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    thread_id = data.thread_id or f"session-{uuid.uuid4().hex[:8]}"
    result = chat_service.send_message(
        db=db,
        current_user=current_user,
        thread_id=thread_id,
        message=data.message,
    )
    return ChatResponse(**result)


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return conv_crud.list_conversations(db, current_user.id, skip=skip, limit=limit)


@router.get("/conversations/{thread_id}", response_model=ConversationOut)
def get_conversation(
    thread_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return conv_crud.get_user_conversation(db, current_user.id, thread_id)


@router.post("/task-outcome", status_code=status.HTTP_200_OK)
def log_task_outcome(
    data: TaskOutcomeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    chat_service.log_task_outcome(
        db=db,
        current_user=current_user,
        thread_id=data.thread_id,
        summary=data.summary,
        outcome=data.outcome,
    )
    return {"status": "success", "message": "Task outcome logged successfully"}


@router.post("/memory/fact", status_code=status.HTTP_201_CREATED)
def add_fact(
    data: MemoryFactCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    memory_service.remember_fact(db=db, owner_id=current_user.id, fact=data.fact)
    return {"status": "success", "message": "Fact saved successfully"}


@router.delete("/memory", response_model=MemoryClearResponse)
def clear_memory(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return memory_service.clear_all_memory(db=db, owner_id=current_user.id)
