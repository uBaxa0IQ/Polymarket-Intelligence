"""add wallet analyses history table

Revision ID: 0022_wallet_analyses_history
Revises: 0021_bet_source_copytrading
Create Date: 2026-04-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0022_wallet_analyses_history"
down_revision = "0021_bet_source_copytrading"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wallet_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("wallet", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="ok", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("source_counts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_wallet_analyses_created_at"), "wallet_analyses", ["created_at"], unique=False)
    op.create_index(op.f("ix_wallet_analyses_wallet"), "wallet_analyses", ["wallet"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_wallet_analyses_wallet"), table_name="wallet_analyses")
    op.drop_index(op.f("ix_wallet_analyses_created_at"), table_name="wallet_analyses")
    op.drop_table("wallet_analyses")
