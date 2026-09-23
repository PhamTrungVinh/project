"""Add booking audit history and transactional outbox.

Revision ID: 20260916_0004
Revises: 20260916_0003
Create Date: 2026-09-16
"""

from alembic import op
import sqlalchemy as sa

revision = "20260916_0004"
down_revision = "20260916_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "booking_audit",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_booking_audit_booking_id", "booking_audit", ["booking_id"])
    op.create_index("ix_booking_audit_owner_id", "booking_audit", ["owner_id"])

    op.create_table(
        "booking_outbox",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("booking_id", sa.Integer(), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("delivery_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
    )
    op.create_index("ix_booking_outbox_booking_id", "booking_outbox", ["booking_id"])
    op.create_index("ix_booking_outbox_event_type", "booking_outbox", ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_booking_outbox_event_type", table_name="booking_outbox")
    op.drop_index("ix_booking_outbox_booking_id", table_name="booking_outbox")
