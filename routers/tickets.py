# routers/tickets.py
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models.user import User
from schemas.ticket import TicketCreate, TicketUpdate, TicketStatusUpdate, TicketOut
from crud import tickets as ticket_crud

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("/", response_model=TicketOut)
def create_ticket(
    data: TicketCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ticket_crud.create_ticket(db, current_user.id, data)


@router.get("/", response_model=list[TicketOut])
def list_tickets(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ticket_crud.list_tickets(db, current_user.id, skip=skip, limit=limit)


@router.get("/{ticket_code}", response_model=TicketOut)
def get_ticket(
    ticket_code: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ticket_crud.get_ticket_by_code(db, current_user.id, ticket_code)


@router.patch("/{ticket_code}", response_model=TicketOut)
def update_ticket(
    ticket_code: str,
    data: TicketUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ticket_crud.update_ticket(db, current_user.id, ticket_code, data)


@router.patch("/{ticket_code}/status", response_model=TicketOut)
def update_ticket_status(
    ticket_code: str,
    data: TicketStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return ticket_crud.update_ticket_status(db, current_user.id, ticket_code, data.status)