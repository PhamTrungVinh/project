from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func

from database import Base


class SemanticMemory(Base):
    __tablename__ = "semantic_memory"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    fact = Column(Text, nullable=False)
    embedding = Column(Text, nullable=False)  # JSON-encoded list[float]
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class EpisodicMemory(Base):
    __tablename__ = "episodic_memory"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    thread_id = Column(String, nullable=True, index=True)
    summary = Column(Text, nullable=False)
    outcome = Column(Text, nullable=False)
    embedding = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())