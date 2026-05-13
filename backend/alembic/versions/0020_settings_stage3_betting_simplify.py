"""Stage3/betting settings simplify: unified slippage_tolerance; drop redundant keys.

Revision ID: 0020
Revises: 0019
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO settings (category, key, value, description)
            SELECT
              'betting',
              'slippage_tolerance',
              COALESCE(
                (SELECT value FROM settings WHERE category = 'betting' AND key = 'slippage_protection' LIMIT 1),
                to_jsonb(0.02::float)
              ),
              'When slippage_protection_enabled: EV slip cost = notional × this fraction; live submit rejects if |best price − theoretical| exceeds this.'
            WHERE NOT EXISTS (
              SELECT 1 FROM settings WHERE category = 'betting' AND key = 'slippage_tolerance'
            );
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM settings
            WHERE (category = 'betting' AND key IN (
              'slippage_protection', 'slippage_cost_bps', 'target_bet_percent'
            ))
            OR (category = 'stage3' AND key = 'confidence_kelly_halve_below');
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO settings (category, key, value, description)
            SELECT 'betting', 'slippage_protection', value,
              'Legacy: max |price diff| at submit; use slippage_tolerance instead.'
            FROM settings
            WHERE category = 'betting' AND key = 'slippage_tolerance'
            ON CONFLICT (category, key) DO NOTHING;
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO settings (category, key, value, description)
            VALUES
              ('betting', 'slippage_cost_bps', to_jsonb(0::float),
               'Legacy slippage bps for EV; 0 = derive from slippage_protection'),
              ('betting', 'target_bet_percent', to_jsonb(0.01::float),
               'Legacy per-bet bankroll fraction cap'),
              ('stage3', 'confidence_kelly_halve_below', to_jsonb(0.6::float),
               'Legacy: halve Kelly when confidence below this')
            ON CONFLICT (category, key) DO NOTHING;
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM settings
            WHERE category = 'betting' AND key = 'slippage_tolerance';
            """
        )
    )
