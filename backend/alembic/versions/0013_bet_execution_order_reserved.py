"""Bets: execution_order_id. Execution_orders: reserved_amount_usd.

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("execution_orders", sa.Column("reserved_amount_usd", sa.Float(), nullable=True))
    op.add_column(
        "bets",
        sa.Column("execution_order_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_bets_execution_order_id", "bets", ["execution_order_id"])
    op.create_foreign_key(
        "fk_bets_execution_order_id",
        "bets",
        "execution_orders",
        ["execution_order_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_bets_execution_order_id", "bets", type_="foreignkey")
    op.drop_index("ix_bets_execution_order_id", table_name="bets")
    op.drop_column("bets", "execution_order_id")
    op.drop_column("execution_orders", "reserved_amount_usd")
