"""Add current_stage to pipeline_runs.

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pipeline_runs", sa.Column("current_stage", sa.String(length=32), nullable=True))
    op.execute("UPDATE settings SET value = '0'::jsonb WHERE category = 'stage3' AND key = 'bankroll_usd'")


def downgrade() -> None:
    op.drop_column("pipeline_runs", "current_stage")
