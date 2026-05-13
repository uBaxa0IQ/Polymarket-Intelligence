"""Insert settlement scheduler settings for existing databases.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO settings (category, key, value, description)
            VALUES
              ('settlement', 'enabled', to_jsonb(false),
               'Periodically sync bet P&L from closed Polymarket markets (Gamma API)'),
              ('settlement', 'interval_hours', to_jsonb(6::float),
               'Hours between settlement syncs (ignored if cron_expression is set)'),
              ('settlement', 'cron_expression', NULL::jsonb,
               'Optional cron for settlement sync (overrides interval_hours)')
            ON CONFLICT (category, key) DO NOTHING;
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM settings WHERE category = 'settlement'"))
