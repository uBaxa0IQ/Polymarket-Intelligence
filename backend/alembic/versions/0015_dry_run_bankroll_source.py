"""betting.dry_run_bankroll_source: clob vs settings for dry-mode sizing.

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO settings (category, key, value, description)
            VALUES (
              'betting',
              'dry_run_bankroll_source',
              to_jsonb('clob'::text),
              'Dry mode only: clob = Kelly sizing from CLOB balance; settings = from stage3.bankroll_usd. Live execution always uses CLOB.'
            )
            ON CONFLICT (category, key) DO NOTHING;
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM settings
            WHERE category = 'betting' AND key = 'dry_run_bankroll_source';
            """
        )
    )
