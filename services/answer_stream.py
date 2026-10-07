"""Expose only answer text from raw model clients running inside LangGraph."""

from langgraph.config import get_config, get_stream_writer


def get_answer_writer():
    try:
        config = get_config()
    except RuntimeError:
        return None
    if not config.get("configurable", {}).get("stream_answer"):
        return None
    writer = get_stream_writer()
    return lambda text: writer({"type": "answer", "text": text})
