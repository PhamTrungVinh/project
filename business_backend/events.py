"""Single-process outbox lifecycle; commits inbox before marking delivery."""
import asyncio
import os
from contextlib import asynccontextmanager

from logger import agent_logger
from scripts.run_outbox_worker import run_once
from services.event_inbox_service import receive_event
from shared_platform.domain_persistence import domain_session, session_factory_for


def publish(event):
    with domain_session("event") as db:
        receive_event(db, event)


def deliver_once():
    return run_once(session_factory_for("ticket"), session_factory_for("booking"), publish)


@asynccontextmanager
async def event_lifespan(app):
    if os.getenv("OUTBOX_WORKER_ENABLED", "true").lower() not in {"true", "1", "yes"}:
        yield
        return
    interval = float(os.getenv("OUTBOX_POLL_SECONDS", "5"))
    if interval <= 0:
        raise RuntimeError("OUTBOX_POLL_SECONDS must be positive")
    stop = asyncio.Event()

    async def run():
        while not stop.is_set():
            try:
                result = await asyncio.to_thread(deliver_once)
                agent_logger.info("outbox_delivery result=%s", result)
            except Exception:
                agent_logger.exception("outbox_delivery_failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except TimeoutError:
                pass

    task = asyncio.create_task(run())
    try:
        yield
    finally:
        stop.set()
        await task
