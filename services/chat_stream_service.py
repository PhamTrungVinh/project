"""SSE transport for a synchronous chat turn with worker-owned DB sessions."""

import asyncio
import json
from queue import Empty, Full, Queue
from threading import Event

from logger import agent_logger
from utils.exceptions import AppException
from fastapi import HTTPException

HEARTBEAT_SECONDS = 10


def encode_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def stream_turn(run_turn, thread_id: str, correlation_id: str):
    """Stop publishing on disconnect; let an already-started turn finish safely."""
    queue = Queue(maxsize=64)
    disconnected = Event()

    def publish(event, data):
        while not disconnected.is_set():
            try:
                queue.put((event, data), timeout=0.1)
                return
            except Full:
                continue

    def work():
        try:
            streamed = False

            def on_delta(text):
                nonlocal streamed
                streamed = True
                publish("delta", {"text": text})

            response = run_turn(on_delta)
            if not streamed:
                # Static replies (approvals, blocked input, fallbacks) have no model tokens.
                import re
                for word in re.findall(r"\S+\s*|\s+", response.answer):
                    on_delta(word)
            publish("result", response.model_dump(mode="json"))
        except (AppException, HTTPException) as exc:
            status = exc.status_code
            detail = exc.message if isinstance(exc, AppException) else exc.detail
            publish("error", {"detail": detail if status < 500 else "Chat is temporarily unavailable.",
                              "status": status, "correlation_id": correlation_id})
        except Exception:
            agent_logger.exception("chat_stream_failed correlation_id=%s", correlation_id)
            publish("error", {"detail": "Chat is temporarily unavailable. Please try again later.",
                              "status": 500, "correlation_id": correlation_id})

    yield encode_event("start", {"thread_id": thread_id, "correlation_id": correlation_id})
    task = asyncio.create_task(asyncio.to_thread(work))
    try:
        while True:
            try:
                event, data = await asyncio.to_thread(queue.get, True, HEARTBEAT_SECONDS)
            except Empty:
                yield ": keep-alive\n\n"
                continue
            yield encode_event(event, data)
            if event in {"result", "error"}:
                break
    finally:
        disconnected.set()
        # Cancellation does not terminate the worker or close its DB session early.
        task.cancel()
