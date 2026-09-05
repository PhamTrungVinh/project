import json
import numpy as np
from sqlalchemy.orm import Session

from logger import db_logger
from models.memory import SemanticMemory, EpisodicMemory


def _cosine(a, b) -> float:
    a, b = np.array(a), np.array(b)
    denominator = np.linalg.norm(a) * np.linalg.norm(b)
    return 0.0 if denominator == 0 else float(np.dot(a, b) / denominator)


def save_fact(db: Session, owner_id: int, fact: str, embedding: list[float]) -> SemanticMemory:
    row = SemanticMemory(owner_id=owner_id, fact=fact, embedding=json.dumps(embedding))
    db.add(row)
    db.commit()
    db.refresh(row)
    db_logger.info("semantic_memory_saved owner_id=%s memory_id=%s", owner_id, row.id)
    return row


def search_facts(db: Session, owner_id: int, query_embedding: list[float], top_k: int = 3) -> list[str]:
    rows = db.query(SemanticMemory).filter(SemanticMemory.owner_id == owner_id).all()
    if not rows:
        db_logger.info("semantic_memory_searched owner_id=%s matches=0", owner_id)
        return []
    scored = [(row.fact, _cosine(query_embedding, json.loads(row.embedding))) for row in rows]
    scored.sort(key=lambda item: item[1], reverse=True)
    result = [fact for fact, _ in scored[:top_k]]
    db_logger.info("semantic_memory_searched owner_id=%s matches=%s", owner_id, len(result))
    return result


def clear_facts(db: Session, owner_id: int) -> int:
    count = db.query(SemanticMemory).filter(SemanticMemory.owner_id == owner_id).delete()
    db.commit()
    db_logger.info("semantic_memory_cleared owner_id=%s count=%s", owner_id, count)
    return count


def save_episode(db: Session, owner_id: int, thread_id: str, summary: str, outcome: str, embedding: list[float]) -> EpisodicMemory:
    row = EpisodicMemory(owner_id=owner_id, thread_id=thread_id, summary=summary, outcome=outcome, embedding=json.dumps(embedding))
    db.add(row)
    db.commit()
    db.refresh(row)
    db_logger.info("episodic_memory_saved owner_id=%s thread_id=%s memory_id=%s", owner_id, thread_id, row.id)
    return row


def search_episodes(db: Session, owner_id: int, query_embedding: list[float], top_k: int = 3) -> list[dict]:
    rows = db.query(EpisodicMemory).filter(EpisodicMemory.owner_id == owner_id).all()
    if not rows:
        db_logger.info("episodic_memory_searched owner_id=%s matches=0", owner_id)
        return []
    scored = [({"summary": row.summary, "outcome": row.outcome}, _cosine(query_embedding, json.loads(row.embedding))) for row in rows]
    scored.sort(key=lambda item: item[1], reverse=True)
    result = [row for row, _ in scored[:top_k]]
    db_logger.info("episodic_memory_searched owner_id=%s matches=%s", owner_id, len(result))
    return result


def clear_episodes(db: Session, owner_id: int) -> int:
    count = db.query(EpisodicMemory).filter(EpisodicMemory.owner_id == owner_id).delete()
    db.commit()
    db_logger.info("episodic_memory_cleared owner_id=%s count=%s", owner_id, count)
    return count
