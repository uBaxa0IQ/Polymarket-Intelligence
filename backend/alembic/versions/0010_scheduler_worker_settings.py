"""Add configurable scheduler settings for worker jobs.

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO settings (category, key, value, description)
            VALUES
              ('scheduler', 'wallet_snapshot_enabled', to_jsonb(true),
               'Whether wallet snapshot scheduler is active'),
              ('scheduler', 'wallet_snapshot_interval_minutes', to_jsonb(5::float),
               'Wallet snapshot interval in minutes'),
              ('scheduler', 'settlement_sync_enabled', to_jsonb(true),
               'Whether settlement sync scheduler is active'),
              ('scheduler', 'settlement_sync_interval_minutes', to_jsonb(30::float),
               'Settlement sync interval in minutes')
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
              AND key IN (
                'wallet_snapshot_enabled',
                'wallet_snapshot_interval_minutes',
                'settlement_sync_enabled',
                'settlement_sync_interval_minutes'
              )
            """
        )
    )
