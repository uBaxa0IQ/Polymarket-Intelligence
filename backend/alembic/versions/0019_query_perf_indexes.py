"""B-tree indexes for common list/filter queries (pipeline, stats, settlement).

Revision ID: 0019
Revises: 0018
"""

from __future__ import annotations

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_pipeline_runs_started_at", "pipeline_runs", ["started_at"], unique=False)
    op.create_index("ix_llm_calls_created_at", "llm_calls", ["created_at"], unique=False)
    op.create_index(
        "ix_llm_calls_pipeline_run_created_at",
        "llm_calls",
        ["pipeline_run_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_bets_resolved_status_placed_at",
        "bets",
        ["resolved", "status", "placed_at"],
        unique=False,
    )
    op.create_index("ix_decisions_analysis_id", "decisions", ["analysis_id"], unique=False)
    op.create_index("ix_bets_decision_id", "bets", ["decision_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_bets_decision_id", table_name="bets")
    op.drop_index("ix_decisions_analysis_id", table_name="decisions")
    op.drop_index("ix_bets_resolved_status_placed_at", table_name="bets")
    op.drop_index("ix_llm_calls_pipeline_run_created_at", table_name="llm_calls")
    op.drop_index("ix_llm_calls_created_at", table_name="llm_calls")
    op.drop_index("ix_pipeline_runs_started_at", table_name="pipeline_runs")
