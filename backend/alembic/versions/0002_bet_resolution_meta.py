"""bet resolution metadata

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bets",
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "bets",
        sa.Column("resolution_source", sa.String(32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("bets", "resolution_source")
    op.drop_column("bets", "resolved_at")
