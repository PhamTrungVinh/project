from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


class ChatResponse(BaseModel):
    answer: str
    route: str | None = None
    thread_id: str


class ChatMessageRequest(BaseModel):
    message: str = Field(min_length=1)
    thread_id: str | None = Field(default=None, min_length=1, max_length=255)


class PendingActionOut(BaseModel):
    id: str
    agent: str
    question: str
    expires_at: datetime


class ChatMessageResponse(ChatResponse):
    pending_actions: list[PendingActionOut]
    correlation_id: str


class PendingActionDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]


class PendingActionDecisionResponse(BaseModel):
    id: str
    status: str
    thread_id: str
    result: str | None = None
    answer: str | None = None
    route: str | None = None
    pending_actions: list[PendingActionOut] = Field(default_factory=list)
    correlation_id: str


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
