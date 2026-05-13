"""Add screener.exclude_open_positions setting.

Revision ID: 0018
Revises: 0017
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO settings (category, key, value, description)
            VALUES (
              'screener',
              'exclude_open_positions',
              'true',
              'Skip markets where the configured wallet already has an open position on Polymarket (fetched from Gamma API at screener time)'
            )
            ON CONFLICT (category, key) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM settings WHERE category = 'screener' AND key = 'exclude_open_positions'"
        )
    )
