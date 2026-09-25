from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


ALLOWED_PAYLOAD_FIELDS = {
    "ticket-service": {"ticket_code", "status", "fields", "changed_field"},
    "booking-service": {"booking_code", "status", "time", "changed_field"},
}
REQUIRED_PAYLOAD_FIELDS = {
    "ticket-service": {"ticket_code", "status"},
    "booking-service": {"booking_code", "status", "time"},
}


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
    event_type: str
    occurred_at: datetime
    producer: str
    schema_version: str = "v1"
    correlation_id: str = Field(min_length=1)
    causation_id: str | None
    payload: dict[str, Any]

    @model_validator(mode="after")
    def validate_event(self):
        allowed = ALLOWED_PAYLOAD_FIELDS.get(self.producer)
        if self.schema_version != "v1" or allowed is None:
            raise ValueError("Unsupported event schema or producer")
        if self.event_type not in {"TicketCreated", "TicketUpdated", "BookingCreated", "BookingUpdated"}:
            raise ValueError("Unsupported event type")
        if self.event_type.startswith("Ticket") != (self.producer == "ticket-service"):
            raise ValueError("Event type and producer do not match")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must include a timezone")
        if not self.payload.keys() <= allowed:
            raise ValueError("Event payload contains unsupported fields")
        if not REQUIRED_PAYLOAD_FIELDS[self.producer] <= self.payload.keys():
            raise ValueError("Event payload is missing required fields")
        return self
