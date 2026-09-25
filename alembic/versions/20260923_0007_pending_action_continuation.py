"""Retain request context and the answer after an explicit decision.

Revision ID: 20260923_0007
Revises: 20260923_0006
"""

from alembic import op
import sqlalchemy as sa


revision = "20260923_0007"
down_revision = "20260923_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pending_actions", sa.Column("request_context_json", sa.Text(), nullable=True))
    op.add_column("pending_actions", sa.Column("decision_answer", sa.Text(), nullable=True))
    op.add_column("pending_actions", sa.Column("decision_route", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("pending_actions", "decision_route")
    op.drop_column("pending_actions", "decision_answer")
    op.drop_column("pending_actions", "request_context_json")
