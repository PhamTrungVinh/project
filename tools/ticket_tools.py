from typing import Optional
from langchain.tools import tool
from fastapi import HTTPException
from config import TICKET_ADAPTER, TICKET_SERVICE_URL

from logger import db_logger, agent_logger
from database import get_db_session
from services import identity_service, ticket_service
from schemas.ticket import TicketCreate, TicketUpdate
from models.ticket import TicketStatus
from utils.exceptions import NotFoundException, ConflictException
from services.memory_service import remember_episode
from services.date_service import format_local_datetime
from services.domain_remote_adapter import domain_request_for_claims

VALID_STATUSES = ["Pending", "Resolving", "Canceled", "Finished"]
LOCKED_STATUSES = ("Finished", "Canceled")  # tickets in these statuses cannot be updated


def build_ticket_tools(owner_id: int, thread_id: str, idempotency_key: str | None = None, claims=None) -> list:
    @tool
    def create_ticket(
        content: str,
        description: str,
        customer_name: Optional[str] = None,
        customer_phone: Optional[str] = None,
        email: Optional[str] = None,
    ) -> str:
        """..."""
        with get_db_session() as db:
            profile_name, profile_email = identity_service.contact_for_owner(db, owner_id)
            data = TicketCreate(
                content=content,
                description=description,
                # Account identity is authoritative; tool-call arguments come from the LLM.
                customer_name=profile_name or customer_name,
                customer_phone=customer_phone,
                email=profile_email or email,
            )
            if TICKET_ADAPTER == "http" and claims is not None:
                ticket = domain_request_for_claims(
                    TICKET_SERVICE_URL, claims, "POST", "/tickets/",
                    data.model_dump(mode="json", exclude_none=True), idempotency_key=idempotency_key,
                )
                ticket_code = ticket["ticket_code"]
            else:
                ticket = ticket_service.create_ticket(db, owner_id, data, idempotency_key, claims)
                ticket_code = ticket.ticket_code

            try:
                remember_episode(db, owner_id, thread_id, f"Created ticket: {content}",
                                f"ticket_code={ticket_code}, status=Pending")
            except Exception as e:
                agent_logger.warning(f"remember_episode failed after ticket created: {e}")

        agent_logger.info(f"TICKET_TOOL create ticket_code={ticket_code} owner_id={owner_id}")
        return f"Created ticket {ticket_code}, status: Pending."

    @tool
    def track_ticket(
        ticket_code: str,
    ) -> str:
        """Track a support ticket by ticket_code.
        Returns full ticket info: content, description, status, customer_name,
        customer_phone, email, creation time.
        Only returns tickets that belong to the current user."""
        with get_db_session() as db:
            try:
                if TICKET_ADAPTER == "http" and claims is not None:
                    ticket = domain_request_for_claims(TICKET_SERVICE_URL, claims, "GET", f"/tickets/{ticket_code}")
                else:
                    ticket = ticket_service.get_ticket(db, owner_id, ticket_code)
            except (NotFoundException, HTTPException):
                return f"Ticket not found with code {ticket_code}."
        if isinstance(ticket, dict):
            return (
                f"ticket_code: {ticket['ticket_code']}\ncontent: {ticket['content']}\n"
                f"description: {ticket['description']}\nstatus: {ticket['status']}\n"
                f"customer_name: {ticket.get('customer_name')}\ncustomer_phone: {ticket.get('customer_phone')}\n"
                f"email: {ticket.get('email')}\ncreated_at: {ticket.get('created_at')}"
            )
        return (
            f"ticket_code: {ticket.ticket_code}\ncontent: {ticket.content}\n"
            f"description: {ticket.description}\nstatus: {ticket.status.value}\n"
            f"customer_name: {ticket.customer_name}\ncustomer_phone: {ticket.customer_phone}\n"
            f"email: {ticket.email}\ncreated_at: {format_local_datetime(ticket.created_at)}"
        )


    @tool
    def update_ticket(
        ticket_code: str,
        content: Optional[str] = None,
        description: Optional[str] = None,
        customer_name: Optional[str] = None,
        customer_phone: Optional[str] = None,
        email: Optional[str] = None,
    ) -> str:
        """Update an existing ticket. Only the fields provided are changed, others stay unchanged.
        Cannot update a ticket that is already 'Finished' or 'Canceled'.
        Valid status values: Pending, Resolving, Canceled, Finished.
        Email is auto-injected from context if not provided directly, but can be overridden."""

        with get_db_session() as db:
            data = TicketUpdate(
                content=content, description=description,
                customer_name=customer_name, customer_phone=customer_phone, email=email,
            )
            try:
                if TICKET_ADAPTER == "http" and claims is not None:
                    domain_request_for_claims(
                        TICKET_SERVICE_URL, claims, "PATCH", f"/tickets/{ticket_code}",
                        data.model_dump(mode="json", exclude_none=True), idempotency_key=idempotency_key,
                    )
                else:
                    ticket_service.update_ticket(db, owner_id, ticket_code, data, idempotency_key)
            except NotFoundException:
                return f"Ticket not found with code {ticket_code}."
            except ConflictException as e:
                remember_episode(db, owner_id, thread_id, f"Tried to update ticket {ticket_code}", f"FAILED - {e.message}")
                return e.message
            except HTTPException as e:
                return str(e.detail)
            remember_episode(db, owner_id, thread_id, f"Updated ticket {ticket_code}", "success")
        return f"Updated ticket {ticket_code}."

    @tool
    def update_ticket_status(ticket_code: str, status: str) -> str:
        """Change a ticket's status. Valid values: Pending, Resolving, Canceled, Finished.
        Valid transitions: Pending -> Resolving -> Finished, or Canceled from Pending/Resolving."""
        with get_db_session() as db:
            try:
                new_status = TicketStatus(status)
            except ValueError:
                return f"Invalid status: {status}. Must be one of Pending, Resolving, Canceled, Finished."
            try:
                if TICKET_ADAPTER == "http" and claims is not None:
                    domain_request_for_claims(
                        TICKET_SERVICE_URL, claims, "PATCH", f"/tickets/{ticket_code}/status",
                        {"status": new_status.value}, idempotency_key=idempotency_key,
                    )
                else:
                    ticket_service.update_ticket_status(db, owner_id, ticket_code, new_status, idempotency_key)
            except NotFoundException:
                return f"Ticket not found with code {ticket_code}."
            except ConflictException as e:
                return e.message
            except HTTPException as e:
                return str(e.detail)
        return f"Ticket {ticket_code} status changed to {status}."

    return [create_ticket, track_ticket, update_ticket, update_ticket_status]
