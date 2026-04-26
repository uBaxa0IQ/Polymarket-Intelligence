"""Refresh betting setting descriptions (seed does not update existing rows).

Revision ID: 0016
Revises: 0015
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE settings
            SET description = 'CLOB order type: IOC (mapped to FAK in py-clob-client), FAK, FOK, GTC, GTD'
            WHERE category = 'betting' AND key = 'order_time_in_force'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE settings
            SET description = 'Enable slippage checks in EV math and order submission guard'
            WHERE category = 'betting' AND key = 'slippage_protection_enabled'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE settings
            SET description = 'Slippage in bps for EV when slippage_protection_enabled=true; 0 = derive from slippage_protection'
            WHERE category = 'betting' AND key = 'slippage_cost_bps'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE settings
            SET description = 'Max allowed price diff fraction for submit-time slippage guard (used only when enabled)'
            WHERE category = 'betting' AND key = 'slippage_protection'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE settings
            SET description = 'Order time-in-force for live CLOB orders: IOC, FOK, or GTC'
            WHERE category = 'betting' AND key = 'order_time_in_force'
            """
        )
    )
