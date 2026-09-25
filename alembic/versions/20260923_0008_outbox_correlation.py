"""Persist correlation and causation IDs with domain outbox records.

Revision ID: 20260923_0008
Revises: 20260923_0007
"""

from alembic import op
import sqlalchemy as sa


revision = "20260923_0008"
down_revision = "20260923_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("ticket_outbox", "booking_outbox"):
        op.add_column(table, sa.Column("correlation_id", sa.String(length=128), nullable=True))
        op.add_column(table, sa.Column("causation_id", sa.String(length=128), nullable=True))


def downgrade() -> None:
    for table in ("booking_outbox", "ticket_outbox"):
        op.drop_column(table, "causation_id")
        op.drop_column(table, "correlation_id")
