from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.sql import func
import enum

from database import Base

class BookingStatus(str, enum.Enum):
    SCHEDULED = "Scheduled"
    CANCELED = "Canceled"
    FINISHED = "Finished"

class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    booking_code = Column(String, unique=True, index=True)  # "BKG-xxxx" hiển thị cho user

    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    reason = Column(String, nullable=False)
    time = Column(DateTime(timezone=True), nullable=False)
    note = Column(String, nullable=True)
    customer_name = Column(String, nullable=True)
    customer_phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    status = Column(
        SAEnum(BookingStatus, native_enum=False),  # native_enum=False -> lưu dạng VARCHAR trong SQLite, tương thích tốt hơn
        default=BookingStatus.SCHEDULED,
        nullable=False,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )