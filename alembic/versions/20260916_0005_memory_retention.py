"""Add retention metadata for user memory.

Revision ID: 20260916_0005
Revises: 20260916_0004
Create Date: 2026-09-16
"""

from alembic import op
import sqlalchemy as sa

revision = "20260916_0005"
down_revision = "20260916_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("semantic_memory", sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.add_column("episodic_memory", sa.Column("expires_at", sa.DateTime(timezone=True)))
    op.create_index("ix_semantic_memory_expires_at", "semantic_memory", ["expires_at"])
    op.create_index("ix_episodic_memory_expires_at", "episodic_memory", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_episodic_memory_expires_at", table_name="episodic_memory")
    op.drop_index("ix_semantic_memory_expires_at", table_name="semantic_memory")
    op.drop_column("episodic_memory", "expires_at")
    op.drop_column("semantic_memory", "expires_at")
