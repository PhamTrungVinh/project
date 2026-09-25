from datetime import datetime, timezone
from pydantic import BaseModel, field_serializer

from booking_service.models import BookingStatus


class BookingCreate(BaseModel):
    reason: str
    time: datetime  # Pydantic parses ISO strings into datetime and reports invalid formats clearly
    note: str | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    email: str | None = None


class BookingUpdate(BaseModel):
    reason: str | None = None
    time: datetime | None = None
    note: str | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    email: str | None = None


class BookingOut(BaseModel):
    id: int
    booking_code: str
    reason: str
    time: datetime
    note: str | None
    customer_name: str | None
    customer_phone: str | None
    email: str | None
    status: BookingStatus
    created_at: datetime
    updated_at: datetime | None

    class Config:
        from_attributes = True
    @field_serializer("time")
    def serialize_time_as_utc(self, value: datetime) -> str:
        """Return an unambiguous UTC ISO timestamp, including SQLite rows."""
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
