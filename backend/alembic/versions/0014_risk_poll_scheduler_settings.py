"""Risk, betting fee, and order-poll / reconcile scheduler settings.

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO settings (category, key, value, description)
            VALUES
              ('betting', 'taker_fee_bps', to_jsonb(0::float),
               'CLOB taker fee in basis points (e.g. 20 = 0.20% for EV after costs)'),
              ('betting', 'slippage_cost_bps', to_jsonb(0::float),
               'Optional slippage in bps for EV; 0 = derive from slippage_protection fraction'),
              ('risk', 'execution_kill_switch', to_jsonb(false),
               'When true, no live orders are placed (check_can_place / betting)'),
              ('risk', 'daily_loss_limit_usd', NULL,
               'Stop new risk after this much realized loss (USD) today (UTC); null = off'),
              ('risk', 'max_exposure_per_market_usd', NULL,
               'Max open exposure per market in USD; null = off'),
              ('scheduler', 'order_poll_enabled', to_jsonb(true),
               'Run global CLOB open-order poller (fills / updates)'),
              ('scheduler', 'order_poll_interval_seconds', to_jsonb(15::float),
               'Interval in seconds for order poll job'),
              ('scheduler', 'reconcile_stale_drafts_enabled', to_jsonb(true),
               'Mark stale draft orders failed and release reserved funds'),
              ('scheduler', 'reconcile_interval_seconds', to_jsonb(60::float),
               'Interval in seconds for stale-draft reconciler'),
              ('scheduler', 'reconcile_older_than_sec', to_jsonb(60::float),
               'Drafts older than this (seconds) are considered stale')
            ON CONFLICT (category, key) DO NOTHING;
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM settings
            WHERE (category, key) IN (
              ('betting', 'taker_fee_bps'),
              ('betting', 'slippage_cost_bps'),
              ('risk', 'execution_kill_switch'),
              ('risk', 'daily_loss_limit_usd'),
              ('risk', 'max_exposure_per_market_usd'),
              ('scheduler', 'order_poll_enabled'),
              ('scheduler', 'order_poll_interval_seconds'),
              ('scheduler', 'reconcile_stale_drafts_enabled'),
              ('scheduler', 'reconcile_interval_seconds'),
              ('scheduler', 'reconcile_older_than_sec')
            );
            """
        )
    )
