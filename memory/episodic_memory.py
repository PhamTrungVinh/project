import json
import numpy as np

from config import embeddings
import db
from logger import db_logger


def _cosine(a, b):
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def save_episode(
    user_id: str,
    conversation_id: str,
    summary: str,
    outcome: str
):
    """Save an episode, e.g., 'User asked about Q3 variance; data quality issue was identified'."""
    emb = embeddings.embed_query(summary)
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO episodic_memory (id, conversation_id, user_id, summary, outcome, embedding, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            db.new_id("EPI"),
            conversation_id,
            user_id,
            summary,
            outcome,
            json.dumps(emb),
            db.now_iso(),
        ),
    )
    conn.commit()
    conn.close()
    db_logger.info(f"Saved episode for user_id={user_id}, conversation_id={conversation_id}, summary={summary}, outcome={outcome}")


def search_episodes(
    user_id: str,
    query: str,
    top_k: int = 3,
) -> list[dict]:
    """Retrieve the most relevant episodes using semantic similarity."""
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT summary, outcome, created_at, embedding "
        "FROM episodic_memory WHERE user_id=?",
        (user_id,),
    ).fetchall()
    conn.close()

    if not rows:
        return []

    query_emb = embeddings.embed_query(query)
    scored = [
        (dict(row), _cosine(query_emb, json.loads(row["embedding"])))
        for row in rows
    ]
    # scored = [(r, s) for r, s in scored if s >= min_score]
    scored.sort(key=lambda x: x[1], reverse=True)

    return [r for r, _ in scored[:top_k]]


def clear_episodes(user_id: str):
    """Clear all episodic memory for a user."""
    conn = db.get_conn()
    conn.execute("DELETE FROM episodic_memory WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    db_logger.info(f"Cleared all episodes for user_id={user_id}")