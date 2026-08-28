import uuid
from sqlalchemy.orm import Session

from models.conversation import Conversation
from utils.exceptions import ForbiddenException, NotFoundException


def create_conversation(db: Session, owner_id: int, thread_id: str | None = None) -> Conversation:
    conv = Conversation(thread_id=thread_id or f"session-{uuid.uuid4().hex[:8]}", owner_id=owner_id)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def get_conversation(db: Session, thread_id: str) -> Conversation | None:
    return db.query(Conversation).filter(Conversation.thread_id == thread_id).first()


def get_user_conversation(db: Session, owner_id: int, thread_id: str) -> Conversation:
    conv = get_conversation(db, thread_id)
    if conv is None:
        raise NotFoundException(f"Conversation not found with thread_id {thread_id}")
    if conv.owner_id != owner_id:
        raise ForbiddenException("This conversation does not belong to you")
    return conv


def list_conversations(db: Session, owner_id: int, skip: int = 0, limit: int = 50) -> list[Conversation]:
    return (
        db.query(Conversation)
        .filter(Conversation.owner_id == owner_id)
        .order_by(Conversation.updated_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_or_create_conversation(db: Session, owner_id: int, thread_id: str) -> Conversation:
    conv = get_conversation(db, thread_id)
    if conv is None:
        return create_conversation(db, owner_id, thread_id)

    if conv.owner_id != owner_id:
        raise ForbiddenException("This conversation does not belong to you")

    return conv


def update_email(db: Session, thread_id: str, email: str) -> Conversation | None:
    conv = get_conversation(db, thread_id)
    if conv:
        conv.email = email
        db.commit()
        db.refresh(conv)
    return conv


def set_title_if_empty(db: Session, thread_id: str, title: str) -> None:
    conv = get_conversation(db, thread_id)
    if conv and not conv.title:
        conv.title = title[:255]
        db.commit()