import sqlite3

from langchain_core.messages import trim_messages, SystemMessage, RemoveMessage
from config import llm
from logger import db_logger

MAX_TOKENS = 4000  # Maximum number of tokens to keep in the context window per LLM call


def trim_working_memory(messages: list) -> list:
    """
    Keep the most recent messages without exceeding MAX_TOKENS.
    Uses the LLM's own token_counter to count tokens accurately
    according to the model being used.
    """
    kept = trim_messages(
        messages,
        max_tokens=MAX_TOKENS,
        token_counter=llm,
        strategy="last",
        include_system=True,
        start_on="human",
    )
    kept_ids = {m.id for m in kept}
    return [RemoveMessage(id=m.id) for m in messages if m.id not in kept_ids]


def summarize_if_needed(messages: list, threshold: int = 20) -> list:
    """
    If the conversation is too long (> threshold messages), summarize
    the older messages into a single SystemMessage while keeping
    the most recent messages unchanged.
    """
    if len(messages) <= threshold:
        return messages

    old_part = messages[:-10]
    recent_part = messages[-10:]

    summary_prompt = (
        "Summarize the following conversation history into a few concise "
        "bullet points capturing key facts, decisions, and open items:\n\n"
        + "\n".join(f"{m.type}: {m.content}" for m in old_part)
    )
    summary = llm.invoke(summary_prompt).content

    return [SystemMessage(content=f"[Earlier conversation summary]\n{summary}")] + recent_part


def clear_working_memory(thread_id: str, db_path: str = "checkpoints.db"):
    """ Clear all working memory (messages) for the current session."""

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("DELETE FROM checkpoints WHERE thread_id=?", (thread_id,))
    cur.execute("DELETE FROM writes WHERE thread_id=?", (thread_id,))
    conn.commit()
    conn.close()
    db_logger.info(f"Cleared all working memory for thread_id={thread_id}")