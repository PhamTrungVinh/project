"""Create the application schema.

Revision ID: 20260905_0001
Revises:
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa

revision = "20260905_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    ticket_status = sa.Enum("PENDING", "RESOLVING", "CANCELED", "FINISHED", name="ticketstatus", native_enum=False)
    booking_status = sa.Enum("SCHEDULED", "CANCELED", "FINISHED", name="bookingstatus", native_enum=False)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_id", "users", ["id"])
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ticket_code", sa.String(), nullable=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("customer_name", sa.String()),
        sa.Column("customer_phone", sa.String()),
        sa.Column("email", sa.String()),
        sa.Column("status", ticket_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_tickets_id", "tickets", ["id"])
    op.create_index("ix_tickets_ticket_code", "tickets", ["ticket_code"], unique=True)
    op.create_index("ix_tickets_owner_id", "tickets", ["owner_id"])

    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("booking_code", sa.String(), nullable=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.String()),
        sa.Column("customer_name", sa.String()),
        sa.Column("customer_phone", sa.String()),
        sa.Column("email", sa.String()),
        sa.Column("status", booking_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_bookings_id", "bookings", ["id"])
    op.create_index("ix_bookings_booking_code", "bookings", ["booking_code"], unique=True)
    op.create_index("ix_bookings_owner_id", "bookings", ["owner_id"])

    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("email", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("title", sa.String(length=255)),
    )
    op.create_index("ix_conversations_id", "conversations", ["id"])
    op.create_index("ix_conversations_thread_id", "conversations", ["thread_id"], unique=True)
    op.create_index("ix_conversations_owner_id", "conversations", ["owner_id"])

    op.create_table(
        "semantic_memory",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("fact", sa.Text(), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_semantic_memory_id", "semantic_memory", ["id"])
    op.create_index("ix_semantic_memory_owner_id", "semantic_memory", ["owner_id"])

    op.create_table(
        "episodic_memory",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("thread_id", sa.String()),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_episodic_memory_id", "episodic_memory", ["id"])
    op.create_index("ix_episodic_memory_owner_id", "episodic_memory", ["owner_id"])
    op.create_index("ix_episodic_memory_thread_id", "episodic_memory", ["thread_id"])


def downgrade() -> None:
    for index in ("ix_episodic_memory_thread_id", "ix_episodic_memory_owner_id", "ix_episodic_memory_id"):
        op.drop_index(index, table_name="episodic_memory")
    op.drop_table("episodic_memory")
    for index in ("ix_semantic_memory_owner_id", "ix_semantic_memory_id"):
        op.drop_index(index, table_name="semantic_memory")
    op.drop_table("semantic_memory")
    for index in ("ix_conversations_owner_id", "ix_conversations_thread_id", "ix_conversations_id"):
        op.drop_index(index, table_name="conversations")
    op.drop_table("conversations")
    for index in ("ix_bookings_owner_id", "ix_bookings_booking_code", "ix_bookings_id"):
        op.drop_index(index, table_name="bookings")
    op.drop_table("bookings")
    for index in ("ix_tickets_owner_id", "ix_tickets_ticket_code", "ix_tickets_id"):
        op.drop_index(index, table_name="tickets")
    op.drop_table("tickets")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_id", table_name="users")
    op.drop_table("users")
