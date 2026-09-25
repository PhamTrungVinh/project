from concurrent.futures import Future, ThreadPoolExecutor
from sqlalchemy import or_
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from database import get_db_session


from crud import memory as memory_crud
from memory_service.models import EpisodicMemory, SemanticMemory
from services.ai_adapter import embed_text
_recording_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="memory-recording")



def _expires_at(retention_days: int | None):
    if retention_days is None:
        return None
    if retention_days < 1:
        raise ValueError("retention_days must be positive")
    return datetime.now(timezone.utc) + timedelta(days=retention_days)


def purge_expired(db: Session, owner_id: int) -> dict:
    """Delete expired semantic and episodic records for one authenticated owner."""
    now = datetime.now(timezone.utc)
    facts = db.query(SemanticMemory).filter(SemanticMemory.owner_id == owner_id, SemanticMemory.expires_at.is_not(None), SemanticMemory.expires_at <= now).delete()
    episodes = db.query(EpisodicMemory).filter(EpisodicMemory.owner_id == owner_id, EpisodicMemory.expires_at.is_not(None), EpisodicMemory.expires_at <= now).delete()
    db.commit()
    return {"facts_deleted": facts, "episodes_deleted": episodes}

def remember_fact(db: Session, owner_id: int, fact: str, retention_days: int | None = None) -> None:
    embedding = embed_text(fact)
    memory_crud.save_fact(db, owner_id, fact, embedding, _expires_at(retention_days))


def recall_facts(db: Session, owner_id: int, query: str, top_k: int = 3) -> list[str]:
    now = datetime.now(timezone.utc)
    if db.query(SemanticMemory.id).filter(
        SemanticMemory.owner_id == owner_id,
        or_(SemanticMemory.expires_at.is_(None), SemanticMemory.expires_at > now),
    ).first() is None:
        return []
    query_embedding = embed_text(query)
    return memory_crud.search_facts(db, owner_id, query_embedding, top_k=top_k)


def remember_episode(db: Session, owner_id: int, thread_id: str, summary: str, outcome: str, retention_days: int | None = None) -> None:
    embedding = embed_text(summary)
    memory_crud.save_episode(db, owner_id, thread_id, summary, outcome, embedding, _expires_at(retention_days))


def recall_episodes(db: Session, owner_id: int, query: str, top_k: int = 3) -> list[dict]:
    now = datetime.now(timezone.utc)
    if db.query(EpisodicMemory.id).filter(
        EpisodicMemory.owner_id == owner_id,
        or_(EpisodicMemory.expires_at.is_(None), EpisodicMemory.expires_at > now),
    ).first() is None:
        return []
    query_embedding = embed_text(query)
    return memory_crud.search_episodes(db, owner_id, query_embedding, top_k=top_k)


def build_memory_context(db: Session, owner_id: int, query: str) -> str:
    facts = recall_facts(db, owner_id, query)
    episodes = recall_episodes(db, owner_id, query)

    parts = []
    if facts:
        parts.append("Known facts about this user:\n" + "\n".join(f"- {f}" for f in facts))
    if episodes:
        parts.append(
            "Possibly relevant past interactions (ignore if not relevant):\n"
            + "\n".join(f"- {e['summary']} -> {e['outcome']}" for e in episodes)
        )
    return "\n\n".join(parts)


def clear_all_memory(db: Session, owner_id: int) -> dict:
    facts_deleted = memory_crud.clear_facts(db, owner_id)
    episodes_deleted = memory_crud.clear_episodes(db, owner_id)
    return {"facts_deleted": facts_deleted, "episodes_deleted": episodes_deleted}

def record_episode_async(owner_id: int, thread_id: str, summary: str, outcome: str, retention_days: int | None = None) -> Future:
    """Record a completed interaction without blocking the chat request."""
    def _record() -> None:
        with get_db_session() as db:
            remember_episode(db, owner_id, thread_id, summary, outcome, retention_days)

    return _recording_executor.submit(_record)
