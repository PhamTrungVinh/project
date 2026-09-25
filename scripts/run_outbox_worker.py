"""Publish ticket and booking outboxes to the durable event inbox."""

import argparse
import json
import os
import random
import time

import httpx
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import get_database_url
from booking_service.models import BookingOutbox
from ticket_service.models import TicketOutbox
from services.booking_outbox_service import dispatch_pending as dispatch_bookings
from services.outbox_service import outbox_stats
from services.ticket_outbox_service import dispatch_pending as dispatch_tickets
from shared_platform.events import EventEnvelope


def session_factory(url: str):
    options = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    return sessionmaker(bind=create_engine(url, **options), autocommit=False, autoflush=False)


def publish_http(event: EventEnvelope) -> None:
    token = os.getenv("EVENT_SERVICE_TOKEN")
    if not token:
        raise RuntimeError("EVENT_SERVICE_TOKEN is required")
    url = os.getenv("EVENT_SERVICE_URL", "http://127.0.0.1:8006").rstrip("/")
    response = httpx.post(
        f"{url}/v1/events",
        json=event.model_dump(mode="json"),
        headers={"X-Internal-Service-Token": token, "X-Request-ID": event.correlation_id},
        timeout=float(os.getenv("EVENT_SERVICE_TIMEOUT_SECONDS", "5")),
    )
    response.raise_for_status()


def run_once(ticket_sessions, booking_sessions, publish=publish_http, *, limit: int = 100) -> dict:
    result = {}
    for name, factory, model, dispatch in (
        ("ticket", ticket_sessions, TicketOutbox, dispatch_tickets),
        ("booking", booking_sessions, BookingOutbox, dispatch_bookings),
    ):
        with factory() as db:
            outcome = dispatch(db, publish, limit=limit)
            result[name] = {
                "published": outcome.published,
                "failed_this_run": outcome.failed,
                **outbox_stats(db, model),
            }
    return result


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Publish one batch and exit")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    args = parser.parse_args()
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")
    default_url = get_database_url()
    ticket_sessions = session_factory(os.getenv("OUTBOX_TICKET_DATABASE_URL", default_url))
    booking_sessions = session_factory(os.getenv("OUTBOX_BOOKING_DATABASE_URL", default_url))
    while True:
        result = run_once(ticket_sessions, booking_sessions, limit=args.limit)
        print(json.dumps(result, sort_keys=True), flush=True)
        if args.once:
            break
        time.sleep(args.poll_seconds + random.uniform(0, min(args.poll_seconds, 1.0)))


if __name__ == "__main__":
    main()
