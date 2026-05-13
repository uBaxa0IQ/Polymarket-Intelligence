"""analyses: debate stats columns for consensus debate loop

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analyses", sa.Column("debate_pairs_completed", sa.Integer(), nullable=True))
    op.add_column("analyses", sa.Column("debate_consensus", sa.Boolean(), nullable=True))
    op.add_column("analyses", sa.Column("debate_stop_reason", sa.String(32), nullable=True))
    op.add_column("analyses", sa.Column("debate_history", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("analyses", "debate_history")
    op.drop_column("analyses", "debate_stop_reason")
    op.drop_column("analyses", "debate_consensus")
    op.drop_column("analyses", "debate_pairs_completed")
