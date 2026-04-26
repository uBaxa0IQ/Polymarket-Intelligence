"""bets: add fee_usd column; create wallet_snapshots table

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bets", sa.Column("fee_usd", sa.Float(), nullable=True))

    op.create_table(
        "wallet_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("collateral_balance_usd", sa.Float(), nullable=True),
        sa.Column("positions_value_usd", sa.Float(), nullable=True),
        sa.Column("total_usd", sa.Float(), nullable=True),
        sa.Column("open_positions_count", sa.Integer(), nullable=True),
        sa.Column("wallet_address", sa.String(64), nullable=True),
    )
    op.create_index("ix_wallet_snapshots_recorded_at", "wallet_snapshots", ["recorded_at"])


def downgrade() -> None:
    op.drop_index("ix_wallet_snapshots_recorded_at", table_name="wallet_snapshots")
    op.drop_table("wallet_snapshots")
    op.drop_column("bets", "fee_usd")
