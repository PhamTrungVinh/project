from datetime import datetime
from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    route: str | None = None
    thread_id: str


class ConversationOut(BaseModel):
    id: int
    thread_id: str
    email: str | None = None
    title: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True


class TaskOutcomeRequest(BaseModel):
    thread_id: str
    summary: str
    outcome: str


class MemoryFactCreate(BaseModel):
    fact: str


class MemoryClearResponse(BaseModel):
    facts_deleted: int
    episodes_deleted: int
