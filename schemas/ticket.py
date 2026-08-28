# schemas/ticket.py
from datetime import datetime
from pydantic import BaseModel

from models.ticket import TicketStatus


class TicketCreate(BaseModel):
    content: str
    description: str
    customer_name: str | None = None
    customer_phone: str | None = None
    email: str | None = None


class TicketUpdate(BaseModel):
    content: str | None = None
    description: str | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    email: str | None = None


class TicketStatusUpdate(BaseModel):
    status: TicketStatus


class TicketOut(BaseModel):
    id: int
    ticket_code: str
    content: str
    description: str
    customer_name: str | None
    customer_phone: str | None
    email: str | None
    status: TicketStatus
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}