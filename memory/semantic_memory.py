import json
import numpy as np
from datetime import datetime

from config import embeddings
import db
from logger import db_logger


def _cosine(a, b):
    a, b = np.array(a), np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def save_fact(user_id: str, fact: str):
    """Save a new fact to semantic memory (e.g., 'User prefers concise summaries')."""
    emb = embeddings.embed_query(fact)
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO semantic_memory (id, user_id, fact, embedding, created_at) VALUES (?,?,?,?,?)",
        (db.new_id("MEM"), user_id, fact, json.dumps(emb), db.now_iso()),
    )
    conn.commit()
    conn.close()
    db_logger.info(f"Saved fact for user_id={user_id}: {fact}")


def search_facts(
    user_id: str,
    query: str,
    top_k: int = 3,
) -> list[str]:
    """Return the top_k facts most relevant to the query for the specified user_id."""
    conn = db.get_conn()
    rows = conn.execute(
        "SELECT fact, embedding FROM semantic_memory WHERE user_id=?", (user_id,)
    ).fetchall()
    conn.close()

    if not rows:
        return []

    query_emb = embeddings.embed_query(query)
    scored = [
        (row["fact"], _cosine(query_emb, json.loads(row["embedding"])))
        for row in rows
    ]
    # scored = [(f, s) for f, s in scored if s >= min_score]
    scored.sort(key=lambda x: x[1], reverse=True)

    return [fact for fact, _ in scored[:top_k]]


def clear_facts(user_id: str):
    """Clear all semantic memory (facts) for a user."""
    conn = db.get_conn()
    conn.execute("DELETE FROM semantic_memory WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    db_logger.info(f"Cleared all facts for user_id={user_id}")