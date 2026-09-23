"""Persist the completed response for durable pending actions.

Revision ID: 20260923_0006
Revises: 20260916_0005
"""

from alembic import op
import sqlalchemy as sa


revision = "20260923_0006"
down_revision = "20260916_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pending_actions",
        sa.Column("execution_result", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pending_actions", "execution_result")
