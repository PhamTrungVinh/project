"""
CRUD cho Semantic + Episodic memory. owner_id là số nguyên (FK tới users.id,
lấy từ JWT đã xác thực), không phải string tự do như bản Streamlit cũ.
"""
import json
import numpy as np
from sqlalchemy.orm import Session

from models.memory import SemanticMemory, EpisodicMemory


def _cosine(a, b) -> float:
    a, b = np.array(a), np.array(b)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def save_fact(db: Session, owner_id: int, fact: str, embedding: list[float]) -> SemanticMemory:
    row = SemanticMemory(owner_id=owner_id, fact=fact, embedding=json.dumps(embedding))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def search_facts(db: Session, owner_id: int, query_embedding: list[float], top_k: int = 3) -> list[str]:
    rows = db.query(SemanticMemory).filter(SemanticMemory.owner_id == owner_id).all()
    if not rows:
        return []
    scored = [(row.fact, _cosine(query_embedding, json.loads(row.embedding))) for row in rows]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [fact for fact, _ in scored[:top_k]]


def clear_facts(db: Session, owner_id: int) -> int:
    count = db.query(SemanticMemory).filter(SemanticMemory.owner_id == owner_id).delete()
    db.commit()
    return count


def save_episode(
    db: Session, owner_id: int, thread_id: str, summary: str, outcome: str, embedding: list[float]
) -> EpisodicMemory:
    row = EpisodicMemory(
        owner_id=owner_id, thread_id=thread_id, summary=summary, outcome=outcome,
        embedding=json.dumps(embedding),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def search_episodes(db: Session, owner_id: int, query_embedding: list[float], top_k: int = 3) -> list[dict]:
    rows = db.query(EpisodicMemory).filter(EpisodicMemory.owner_id == owner_id).all()
    if not rows:
        return []
    scored = [
        ({"summary": row.summary, "outcome": row.outcome}, _cosine(query_embedding, json.loads(row.embedding)))
        for row in rows
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [r for r, _ in scored[:top_k]]


def clear_episodes(db: Session, owner_id: int) -> int:
    count = db.query(EpisodicMemory).filter(EpisodicMemory.owner_id == owner_id).delete()
    db.commit()
    return count