"""Durable inbox shared by HTTP ingestion and in-process outbox delivery."""
import json

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from event_service.app import EventInbox


def receive_event(db, event):
    encoded = json.dumps(event.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    existing = db.get(EventInbox, event.event_id)
    if existing is not None:
        if existing.envelope_json != encoded:
            raise HTTPException(status_code=409, detail="Event ID already has different content")
        return {"status": "duplicate", "event_id": event.event_id}
    db.add(EventInbox(event_id=event.event_id, envelope_json=encoded))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.get(EventInbox, event.event_id)
        if existing is None or existing.envelope_json != encoded:
            raise HTTPException(status_code=409, detail="Event ID already has different content")
        return {"status": "duplicate", "event_id": event.event_id}
    return {"status": "accepted", "event_id": event.event_id}
