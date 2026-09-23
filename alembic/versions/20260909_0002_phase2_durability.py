"""Add Phase 2 idempotency and pending-action persistence.

Revision ID: 20260909_0002
Revises: 20260905_0001
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa

revision = "20260909_0002"
down_revision = "20260905_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "idempotency_records",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_body", sa.Text()),
        sa.Column("status_code", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("owner_id", "idempotency_key", name="uq_idempotency_owner_key"),
    )
    op.create_index("ix_idempotency_records_owner_id", "idempotency_records", ["owner_id"])

    op.create_table(
        "pending_actions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("thread_id", sa.String(length=255), nullable=False),
        sa.Column("agent", sa.String(length=50), nullable=False),
        sa.Column("action_name", sa.String(length=100), nullable=False),
        sa.Column("arguments_json", sa.Text(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pending_actions_owner_id", "pending_actions", ["owner_id"])
    op.create_index("ix_pending_actions_thread_id", "pending_actions", ["thread_id"])
    op.create_index("ix_pending_actions_status", "pending_actions", ["status"])
    op.create_index("ix_pending_actions_owner_thread_status", "pending_actions", ["owner_id", "thread_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_pending_actions_owner_thread_status", table_name="pending_actions")
    op.drop_index("ix_pending_actions_status", table_name="pending_actions")
    op.drop_index("ix_pending_actions_thread_id", table_name="pending_actions")
    op.drop_index("ix_pending_actions_owner_id", table_name="pending_actions")
    op.drop_table("pending_actions")
    op.drop_index("ix_idempotency_records_owner_id", table_name="idempotency_records")
    op.drop_table("idempotency_records")
