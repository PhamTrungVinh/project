"""Compatibility imports for ticket-owned models."""

from ticket_service.models import Ticket, TicketAudit, TicketOutbox, TicketStatus

__all__ = ["Ticket", "TicketAudit", "TicketOutbox", "TicketStatus"]
