"""Authenticated event receiver with durable event-ID deduplication."""

import json
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy import Column, DateTime, String, Text, create_engine, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from shared_platform.events import EventEnvelope
from shared_platform.request_context import request_context_middleware


Base = declarative_base()


class EventInbox(Base):
    __tablename__ = "event_inbox"

    event_id = Column(String(36), primary_key=True)
    envelope_json = Column(Text, nullable=False)
    received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


def create_app(database_url: str | None = None) -> FastAPI:
    url = database_url or os.getenv("EVENT_DATABASE_URL", "sqlite:///./events.db")
    options = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **options)
    sessions = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    def get_db():
        with sessions() as db:
            yield db

    def authorize(x_internal_service_token: str | None = Header(default=None)):
        expected = os.getenv("EVENT_SERVICE_TOKEN")
        if not expected or not x_internal_service_token or not secrets.compare_digest(x_internal_service_token, expected):
            raise HTTPException(status_code=401, detail="Invalid internal service credentials")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if not os.getenv("EVENT_SERVICE_TOKEN"):
            raise RuntimeError("EVENT_SERVICE_TOKEN is required")
        yield
        engine.dispose()

    app = FastAPI(title="Event Inbox", version="v1", lifespan=lifespan)
    app.middleware("http")(request_context_middleware)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/v1/events", dependencies=[Depends(authorize)])
    def receive(event: EventEnvelope, db: Session = Depends(get_db)):
        from services.event_inbox_service import receive_event
        return receive_event(db, event)

    @app.get("/v1/events/{event_id}", dependencies=[Depends(authorize)])
    def get_event(event_id: str, db: Session = Depends(get_db)):
        item = db.get(EventInbox, event_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Event not found")
        return json.loads(item.envelope_json)

    @app.get("/metrics")
    def metrics(db: Session = Depends(get_db)):
        count = db.query(EventInbox).count()
        return {"events_received_total": count}

    return app


app = create_app()
