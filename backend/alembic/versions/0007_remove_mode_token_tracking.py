"""Remove mode columns, add dry_run status, token tracking, screener/ranker results

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── pipeline_runs ──────────────────────────────────────────────────────────
    # Drop mode column
    op.drop_column("pipeline_runs", "mode")
    # Add screener/ranker result storage
    op.add_column("pipeline_runs", sa.Column("screener_results", JSONB, nullable=True))
    op.add_column("pipeline_runs", sa.Column("ranker_results", JSONB, nullable=True))

    # ── bets ───────────────────────────────────────────────────────────────────
    # Drop mode column
    op.drop_column("bets", "mode")
    # Add dry_run to status enum — PostgreSQL requires explicit type alteration
    op.execute("ALTER TYPE bet_status ADD VALUE IF NOT EXISTS 'dry_run'")

    # ── llm_calls ──────────────────────────────────────────────────────────────
    op.add_column("llm_calls", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("llm_calls", sa.Column("output_tokens", sa.Integer(), nullable=True))
    op.add_column("llm_calls", sa.Column("cost_usd", sa.Float(), nullable=True))
    op.add_column("llm_calls", sa.Column("retry_count", sa.Integer(), nullable=True, server_default="0"))
    op.add_column("llm_calls", sa.Column("retry_reason", sa.String(32), nullable=True))

    # ── analyses ───────────────────────────────────────────────────────────────
    op.add_column("analyses", sa.Column("failed_stages", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("analyses", "failed_stages")

    op.drop_column("llm_calls", "retry_reason")
    op.drop_column("llm_calls", "retry_count")
    op.drop_column("llm_calls", "cost_usd")
    op.drop_column("llm_calls", "output_tokens")
    op.drop_column("llm_calls", "input_tokens")

    # Restore bets.mode (enum value dry_run cannot be removed from PG without recreation)
    op.add_column("bets", sa.Column("mode", sa.String(16), nullable=False, server_default="live"))

    op.drop_column("pipeline_runs", "ranker_results")
    op.drop_column("pipeline_runs", "screener_results")
    op.add_column("pipeline_runs", sa.Column("mode", sa.String(16), nullable=False, server_default="live"))
