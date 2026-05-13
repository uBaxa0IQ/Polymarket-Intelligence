"""Drop obsolete settlement settings and scheduler.mode from settings table.

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-22
"""
from __future__ import annotations

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM settings WHERE category = 'settlement'")
    op.execute("DELETE FROM settings WHERE category = 'scheduler' AND key = 'mode'")


def downgrade() -> None:
    # Intentionally empty — legacy rows are optional to restore
    pass
