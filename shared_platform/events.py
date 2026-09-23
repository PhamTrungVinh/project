from dataclasses import dataclass
from datetime import datetime
from typing import Any

@dataclass(frozen=True)
class EventEnvelope:
    event_id: str
    event_type: str
    occurred_at: datetime
    producer: str
    schema_version: str
    correlation_id: str
    causation_id: str | None
    payload: dict[str, Any]

