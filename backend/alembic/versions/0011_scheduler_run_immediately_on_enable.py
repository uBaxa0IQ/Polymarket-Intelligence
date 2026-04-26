"""Add scheduler.run_immediately_on_enable setting.

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO settings (category, key, value, description)
            VALUES
              ('scheduler', 'run_immediately_on_enable', to_jsonb(false),
               'Run pipeline immediately when auto-run is switched on')
            ON CONFLICT (category, key) DO NOTHING;
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM settings
            WHERE category = 'scheduler'
              AND key = 'run_immediately_on_enable'
            """
        )
    )
