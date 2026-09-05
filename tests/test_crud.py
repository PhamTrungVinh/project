import pytest
from sqlalchemy.orm import Session

from models.user import User
from models.ticket import TicketStatus
from models.booking import BookingStatus
from schemas.user import UserCreate
from schemas.ticket import TicketCreate, TicketUpdate
from schemas.booking import BookingCreate, BookingUpdate
from crud import users as user_crud
from crud import tickets as ticket_crud
from crud import bookings as booking_crud
from crud import memory as memory_crud
from utils.exceptions import NotFoundException, ConflictException


def test_user_crud(db_session: Session):
    user_in = UserCreate(email="crud_user@test.com", password="passWORD123", full_name="CRUD User")
    created = user_crud.create_user(db_session, user_in)
    assert created.id is not None
    assert created.email == "crud_user@test.com"
    assert created.full_name == "CRUD User"

    fetched_by_id = user_crud.get_user_by_id(db_session, created.id)
    assert fetched_by_id is not None
    assert fetched_by_id.email == "crud_user@test.com"

    fetched_by_email = user_crud.get_user_by_email(db_session, "crud_user@test.com")
    assert fetched_by_email is not None
    assert fetched_by_email.id == created.id

    assert user_crud.get_user_by_email(db_session, "nonexistent@test.com") is None


def test_ticket_crud(db_session: Session, test_user: User, test_user_2: User):
    ticket_in = TicketCreate(
        content="Monitor flicker",
        description="Monitor flickers on HDMI port",
        customer_name="Alice",
        customer_phone="0987654321",
        email="alice@example.com",
    )
    ticket = ticket_crud.create_ticket(db_session, test_user.id, ticket_in)
    assert ticket.id is not None
    assert ticket.ticket_code.startswith("TCK-")
    assert ticket.status == TicketStatus.PENDING
    assert ticket.owner_id == test_user.id

    # Fetching by ticket code
    fetched = ticket_crud.get_ticket_by_code(db_session, test_user.id, ticket.ticket_code)
    assert fetched.content == "Monitor flicker"

    # User isolation: user 2 cannot see user 1's ticket
    with pytest.raises(NotFoundException):
        ticket_crud.get_ticket_by_code(db_session, test_user_2.id, ticket.ticket_code)

    # List tickets
    user1_tickets = ticket_crud.list_tickets(db_session, test_user.id)
    assert len(user1_tickets) >= 1
    assert any(t.ticket_code == ticket.ticket_code for t in user1_tickets)

    # Update ticket
    update_data = TicketUpdate(description="Updated description")
    updated = ticket_crud.update_ticket(db_session, test_user.id, ticket.ticket_code, update_data)
    assert updated.description == "Updated description"

    # Change status to Resolving then Finished
    ticket_crud.update_ticket_status(db_session, test_user.id, ticket.ticket_code, TicketStatus.RESOLVING)
    ticket_crud.update_ticket_status(db_session, test_user.id, ticket.ticket_code, TicketStatus.FINISHED)

    # Cannot update locked ticket
    with pytest.raises(ConflictException):
        ticket_crud.update_ticket(db_session, test_user.id, ticket.ticket_code, TicketUpdate(content="New content"))

    with pytest.raises(ConflictException):
        ticket_crud.update_ticket_status(db_session, test_user.id, ticket.ticket_code, TicketStatus.PENDING)


def test_booking_crud(db_session: Session, test_user: User, test_user_2: User):
    booking_in = BookingCreate(
        reason="Project discussion",
        time="2026-09-10 14:00",
        note="Need projector",
        customer_name="Bob",
        customer_phone="0912345678",
        email="bob@example.com",
    )
    booking = booking_crud.create_booking(db_session, test_user.id, booking_in)
    assert booking.id is not None
    assert booking.booking_code.startswith("BKG-")
    assert booking.status == BookingStatus.SCHEDULED

    # Fetching by code
    fetched = booking_crud.get_booking_by_code(db_session, test_user.id, booking.booking_code)
    assert fetched.reason == "Project discussion"

    # Isolation check
    with pytest.raises(NotFoundException):
        booking_crud.get_booking_by_code(db_session, test_user_2.id, booking.booking_code)

    # List bookings
    bookings = booking_crud.list_bookings(db_session, test_user.id)
    assert len(bookings) >= 1

    # Update booking
    updated = booking_crud.update_booking(
        db_session, test_user.id, booking.booking_code, BookingUpdate(note="Updated note")
    )
    assert updated.note == "Updated note"

    # Cancel booking
    canceled = booking_crud.cancel_booking(db_session, test_user.id, booking.booking_code)
    assert canceled.status == BookingStatus.CANCELED


def test_memory_crud(db_session: Session, test_user: User):
    embedding1 = [1.0, 0.0, 0.0]
    embedding2 = [0.0, 1.0, 0.0]

    # Semantic facts
    fact1 = memory_crud.save_fact(db_session, test_user.id, "Prefers window seat", embedding1)
    fact2 = memory_crud.save_fact(db_session, test_user.id, "Uses Macbook M3", embedding2)

    results = memory_crud.search_facts(db_session, test_user.id, [0.9, 0.1, 0.0], top_k=1)
    assert len(results) == 1
    assert results[0] == "Prefers window seat"

    # Episodic memory
    episode = memory_crud.save_episode(
        db_session,
        test_user.id,
        "session-1",
        "Booked Room A",
        "Success",
        embedding1,
    )
    assert episode.id is not None

    episodes = memory_crud.search_episodes(db_session, test_user.id, [1.0, 0.0, 0.0], top_k=1)
    assert len(episodes) == 1
    assert episodes[0]["summary"] == "Booked Room A"

    # Clear memory
    cleared_facts = memory_crud.clear_facts(db_session, test_user.id)
    assert cleared_facts >= 2

    cleared_episodes = memory_crud.clear_episodes(db_session, test_user.id)
    assert cleared_episodes >= 1
