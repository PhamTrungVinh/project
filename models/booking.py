"""Compatibility imports for booking-owned models."""

from booking_service.models import Booking, BookingAudit, BookingOutbox, BookingStatus

__all__ = ["Booking", "BookingAudit", "BookingOutbox", "BookingStatus"]
