"""llm_calls.call_metadata for Yandex web search mode + usage

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_calls",
        sa.Column("call_metadata", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llm_calls", "call_metadata")
