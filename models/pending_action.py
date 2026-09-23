import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.sql import func

from database import Base


class PendingAction(Base):
    __tablename__ = "pending_actions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    thread_id = Column(String(255), nullable=False, index=True)
    agent = Column(String(50), nullable=False)
    action_name = Column(String(100), nullable=False)
    arguments_json = Column(Text, nullable=False)
    question = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    idempotency_key = Column(String(255), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    executed_at = Column(DateTime(timezone=True), nullable=True)
    execution_result = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


Index("ix_pending_actions_owner_thread_status", PendingAction.owner_id, PendingAction.thread_id, PendingAction.status)
