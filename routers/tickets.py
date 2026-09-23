from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from config import TICKET_ADAPTER
from database import get_db
from dependencies import get_current_user
from models.user import User
from schemas.ticket import TicketCreate, TicketUpdate, TicketStatusUpdate, TicketOut
from services import ticket_service
from services.domain_remote_adapter import ticket_request
from services.identity_service import claims_for_user

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("/", response_model=TicketOut)
def create_ticket(
    data: TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if TICKET_ADAPTER == "http":
        return ticket_request(
            current_user, "POST", "/tickets/",
            data.model_dump(mode="json", exclude_none=True),
            idempotency_key=idempotency_key,
        )
    return ticket_service.create_ticket(db, current_user.id, data, idempotency_key, claims_for_user(current_user))


@router.get("/", response_model=list[TicketOut])
def list_tickets(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if TICKET_ADAPTER == "http":
        return ticket_request(current_user, "GET", "/tickets/", query={"skip": skip, "limit": limit})
    return ticket_service.list_tickets(db, current_user.id, skip=skip, limit=limit)


@router.get("/{ticket_code}", response_model=TicketOut)
def get_ticket(
    ticket_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if TICKET_ADAPTER == "http":
        return ticket_request(current_user, "GET", f"/tickets/{ticket_code}")
    return ticket_service.get_ticket(db, current_user.id, ticket_code)


@router.patch("/{ticket_code}", response_model=TicketOut)
def update_ticket(
    ticket_code: str,
    data: TicketUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if TICKET_ADAPTER == "http":
        return ticket_request(
            current_user, "PATCH", f"/tickets/{ticket_code}",
            data.model_dump(mode="json", exclude_none=True), idempotency_key=idempotency_key,
        )
    return ticket_service.update_ticket(db, current_user.id, ticket_code, data, idempotency_key)


@router.patch("/{ticket_code}/status", response_model=TicketOut)
def update_ticket_status(
    ticket_code: str,
    data: TicketStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if TICKET_ADAPTER == "http":
        return ticket_request(
            current_user, "PATCH", f"/tickets/{ticket_code}/status",
            data.model_dump(mode="json"), idempotency_key=idempotency_key,
        )
    return ticket_service.update_ticket_status(db, current_user.id, ticket_code, data.status, idempotency_key)
