"""Claim-authorized ticket service API; it never reads the identity database."""

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from shared_platform.domain_persistence import domain_dependency

from shared_platform.claims_dependency import get_current_claims
from ticket_service.models import TicketStatus
from schemas.ticket import TicketCreate, TicketOut, TicketStatusUpdate, TicketUpdate
from services import ticket_service
from shared_platform.auth_claims import AuthClaims

get_ticket_db = domain_dependency("ticket")
router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("/", response_model=TicketOut)
def create_ticket(data: TicketCreate, db: Session = Depends(get_ticket_db), claims: AuthClaims = Depends(get_current_claims), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    return ticket_service.create_ticket(db, claims.subject_id, data, idempotency_key, claims)


@router.get("/", response_model=list[TicketOut])
def list_tickets(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_ticket_db), claims: AuthClaims = Depends(get_current_claims)):
    return ticket_service.list_tickets(db, claims.subject_id, skip, limit)


@router.get("/{ticket_code}", response_model=TicketOut)
def get_ticket(ticket_code: str, db: Session = Depends(get_ticket_db), claims: AuthClaims = Depends(get_current_claims)):
    return ticket_service.get_ticket(db, claims.subject_id, ticket_code)


@router.patch("/{ticket_code}", response_model=TicketOut)
def update_ticket(ticket_code: str, data: TicketUpdate, db: Session = Depends(get_ticket_db), claims: AuthClaims = Depends(get_current_claims), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    return ticket_service.update_ticket(db, claims.subject_id, ticket_code, data, idempotency_key)


@router.patch("/{ticket_code}/status", response_model=TicketOut)
def update_ticket_status(ticket_code: str, data: TicketStatusUpdate, db: Session = Depends(get_ticket_db), claims: AuthClaims = Depends(get_current_claims), idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    return ticket_service.update_ticket_status(db, claims.subject_id, ticket_code, TicketStatus(data.status), idempotency_key)
