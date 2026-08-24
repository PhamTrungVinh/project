from datetime import datetime
from pydantic import BaseModel

from models.ticket import TicketStatus


class TicketCreate(BaseModel):
    content: str
    description: str
    customer_name: str | None = None
    customer_phone: str | None = None
    email: str | None = None  # nếu không truyền, backend tự inject từ context/conversation


class TicketUpdate(BaseModel):
    """Tất cả field optional - chỉ field nào được truyền mới bị cập nhật."""
    content: str | None = None
    description: str | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    email: str | None = None
    status: TicketStatus | None = None


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

    class Config:
        from_attributes = True