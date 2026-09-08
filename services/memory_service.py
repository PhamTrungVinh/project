from sqlalchemy.orm import Session

from crud import memory as memory_crud
from models.memory import EpisodicMemory, SemanticMemory
from services.ai_adapter import embed_text


def remember_fact(db: Session, owner_id: int, fact: str) -> None:
    embedding = embed_text(fact)
    memory_crud.save_fact(db, owner_id, fact, embedding)


def recall_facts(db: Session, owner_id: int, query: str, top_k: int = 3) -> list[str]:
    if db.query(SemanticMemory.id).filter(SemanticMemory.owner_id == owner_id).first() is None:
        return []
    query_embedding = embed_text(query)
    return memory_crud.search_facts(db, owner_id, query_embedding, top_k=top_k)


def remember_episode(db: Session, owner_id: int, thread_id: str, summary: str, outcome: str) -> None:
    embedding = embed_text(summary)
    memory_crud.save_episode(db, owner_id, thread_id, summary, outcome, embedding)


def recall_episodes(db: Session, owner_id: int, query: str, top_k: int = 3) -> list[dict]:
    if db.query(EpisodicMemory.id).filter(EpisodicMemory.owner_id == owner_id).first() is None:
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