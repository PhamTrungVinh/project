from datetime import datetime
from pydantic import BaseModel

from models.booking import BookingStatus


class BookingCreate(BaseModel):
    reason: str
    time: datetime  # Pydantic tự parse chuỗi ISO thành datetime, báo lỗi rõ ràng nếu sai định dạng
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