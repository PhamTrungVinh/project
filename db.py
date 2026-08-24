"""
Simple SQLite storage for Tickets, Bookings, and Conversation Context.
"""
import sqlite3
import uuid
from datetime import datetime, timezone
from logger import db_logger

DB_PATH = "app.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id TEXT PRIMARY KEY,
            content TEXT,
            description TEXT,
            customer_name TEXT,
            customer_phone TEXT,
            email TEXT,
            time TEXT,
            status TEXT,
            user_id TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            booking_id TEXT PRIMARY KEY,
            customer_name TEXT,
            customer_phone TEXT,
            email TEXT,
            reason TEXT,
            time TEXT,
            note TEXT,
            status TEXT,
            user_id TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS conversation_context (
            conversation_id TEXT PRIMARY KEY,
            user_id TEXT,
            email TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS semantic_memory (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            fact TEXT,
            embedding BLOB,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS episodic_memory (
            id TEXT PRIMARY KEY,
            conversation_id TEXT,
            user_id TEXT,
            summary TEXT,
            outcome TEXT,
            embedding BLOB,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def upsert_conversation_context(conversation_id: str, user_id: str | None, email: str | None):
    """Inserts or updates the conversation context. Used when a new email is detected."""
    if not email:
        return
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT conversation_id FROM conversation_context WHERE conversation_id=?", (conversation_id,))
    row = cur.fetchone()
    ts = now_iso()
    if row:
        cur.execute(
            "UPDATE conversation_context SET email=?, updated_at=? WHERE conversation_id=?",
            (email, ts, conversation_id),
        )
    else:
        cur.execute(
            "INSERT INTO conversation_context (conversation_id, user_id, email, created_at, updated_at) "
            "VALUES (?,?,?,?,?)",
            (conversation_id, user_id, email, ts, ts),
        )
    conn.commit()
    conn.close()
    db_logger.info(f"upsert_conversation_context conversation_id={conversation_id} user_id={user_id} email={email}")


init_db()
