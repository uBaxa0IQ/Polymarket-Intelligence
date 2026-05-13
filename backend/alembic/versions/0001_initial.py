"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-18
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM, JSONB, UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _create_pg_enum_if_not_exists(name: str, values: tuple[str, ...]) -> None:
    """Create a PostgreSQL enum if missing (safe after failed/partial migrations)."""
    literal = ", ".join(repr(v) for v in values)
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            f"CREATE TYPE {name} AS ENUM ({literal}); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        )
    )


def upgrade() -> None:
    # --- Enums (once; columns use postgresql.ENUM(..., create_type=False) — sa.Enum ignores create_type) ---
    _create_pg_enum_if_not_exists(
        "pipeline_status", ("pending", "running", "completed", "failed", "cancelled")
    )
    _create_pg_enum_if_not_exists("pipeline_trigger", ("manual", "scheduled"))
    _create_pg_enum_if_not_exists("pipeline_mode", ("live", "sandbox"))
    _create_pg_enum_if_not_exists("decision_action", ("bet_yes", "bet_no", "skip"))
    _create_pg_enum_if_not_exists("bet_side", ("yes", "no"))
    _create_pg_enum_if_not_exists("bet_mode", ("live", "sandbox"))
    _create_pg_enum_if_not_exists(
        "bet_status", ("pending", "filled", "partial", "failed", "cancelled")
    )

    # --- pipeline_runs ---
    op.create_table(
        "pipeline_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            PG_ENUM(
                "pending",
                "running",
                "completed",
                "failed",
                "cancelled",
                name="pipeline_status",
                create_type=False,
            ),
            default="pending",
        ),
        sa.Column(
            "trigger",
            PG_ENUM("manual", "scheduled", name="pipeline_trigger", create_type=False),
            default="manual",
        ),
        sa.Column(
            "mode",
            PG_ENUM("live", "sandbox", name="pipeline_mode", create_type=False),
            default="sandbox",
        ),
        sa.Column("config_snapshot", JSONB, nullable=True),
        sa.Column("markets_screened", sa.Integer, default=0),
        sa.Column("markets_ranked", sa.Integer, default=0),
        sa.Column("markets_analyzed", sa.Integer, default=0),
        sa.Column("decisions_count", sa.Integer, default=0),
        sa.Column("bets_placed", sa.Integer, default=0),
        sa.Column("error_message", sa.Text, nullable=True),
    )

    # --- markets ---
    op.create_table(
        "markets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("market_id", sa.String(64), unique=True, nullable=False),
        sa.Column("condition_id", sa.String(128), nullable=True),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("market_slug", sa.String(256), nullable=True),
        sa.Column("event_id", sa.String(64), nullable=True),
        sa.Column("event_title", sa.Text, nullable=True),
        sa.Column("tags", JSONB, nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_markets_market_id", "markets", ["market_id"])

    # --- market_snapshots ---
    op.create_table(
        "market_snapshots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("market_id", sa.String(64), sa.ForeignKey("markets.market_id"), nullable=False),
        sa.Column("pipeline_run_id", UUID(as_uuid=True), sa.ForeignKey("pipeline_runs.id"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("yes_implied", sa.Float, nullable=True),
        sa.Column("no_implied", sa.Float, nullable=True),
        sa.Column("volume", sa.Float, nullable=True),
        sa.Column("hours_left", sa.Float, nullable=True),
    )
    op.create_index("ix_market_snapshots_market_id", "market_snapshots", ["market_id"])
    op.create_index("ix_market_snapshots_run_id", "market_snapshots", ["pipeline_run_id"])

    # --- llm_calls ---
    op.create_table(
        "llm_calls",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("pipeline_run_id", UUID(as_uuid=True), sa.ForeignKey("pipeline_runs.id"), nullable=False),
        sa.Column("market_id", sa.String(64), sa.ForeignKey("markets.market_id"), nullable=True),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("system_prompt", sa.Text, nullable=True),
        sa.Column("user_prompt", sa.Text, nullable=True),
        sa.Column("response_raw", sa.Text, nullable=True),
        sa.Column("response_parsed", JSONB, nullable=True),
        sa.Column("temperature", sa.Float, nullable=True),
        sa.Column("max_tokens", sa.Integer, nullable=True),
        sa.Column("web_search_enabled", sa.Boolean, default=False),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("error", sa.Text, nullable=True),
    )
    op.create_index("ix_llm_calls_run_id", "llm_calls", ["pipeline_run_id"])
    op.create_index("ix_llm_calls_market_id", "llm_calls", ["market_id"])

    # --- analyses ---
    op.create_table(
        "analyses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("pipeline_run_id", UUID(as_uuid=True), sa.ForeignKey("pipeline_runs.id"), nullable=False),
        sa.Column("market_id", sa.String(64), sa.ForeignKey("markets.market_id"), nullable=False),
        sa.Column("research_priority", sa.String(16), nullable=True),
        sa.Column("structural_reason", sa.Text, nullable=True),
        sa.Column("evidence_pool", JSONB, nullable=True),
        sa.Column("p_yes", sa.Float, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("p_market", sa.Float, nullable=True),
        sa.Column("gap", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_analyses_run_id", "analyses", ["pipeline_run_id"])
    op.create_index("ix_analyses_market_id", "analyses", ["market_id"])

    # --- decisions ---
    op.create_table(
        "decisions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("pipeline_run_id", UUID(as_uuid=True), sa.ForeignKey("pipeline_runs.id"), nullable=False),
        sa.Column("analysis_id", UUID(as_uuid=True), sa.ForeignKey("analyses.id"), nullable=False),
        sa.Column("market_id", sa.String(64), sa.ForeignKey("markets.market_id"), nullable=False),
        sa.Column(
            "action",
            PG_ENUM("bet_yes", "bet_no", "skip", name="decision_action", create_type=False),
            nullable=False,
        ),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("kelly_fraction", sa.Float, nullable=True),
        sa.Column("bet_size_usd", sa.Float, nullable=True),
        sa.Column("p_yes", sa.Float, nullable=True),
        sa.Column("p_market", sa.Float, nullable=True),
        sa.Column("gap", sa.Float, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("bankroll_usd", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_decisions_run_id", "decisions", ["pipeline_run_id"])
    op.create_index("ix_decisions_market_id", "decisions", ["market_id"])

    # --- bets ---
    op.create_table(
        "bets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("decision_id", UUID(as_uuid=True), sa.ForeignKey("decisions.id"), nullable=False),
        sa.Column("pipeline_run_id", UUID(as_uuid=True), sa.ForeignKey("pipeline_runs.id"), nullable=False),
        sa.Column("market_id", sa.String(64), sa.ForeignKey("markets.market_id"), nullable=False),
        sa.Column("condition_id", sa.String(128), nullable=True),
        sa.Column("side", PG_ENUM("yes", "no", name="bet_side", create_type=False), nullable=False),
        sa.Column("amount_usd", sa.Float, nullable=False),
        sa.Column("price", sa.Float, nullable=True),
        sa.Column("shares", sa.Float, nullable=True),
        sa.Column("mode", PG_ENUM("live", "sandbox", name="bet_mode", create_type=False), nullable=False),
        sa.Column(
            "status",
            PG_ENUM(
                "pending",
                "filled",
                "partial",
                "failed",
                "cancelled",
                name="bet_status",
                create_type=False,
            ),
            default="pending",
        ),
        sa.Column("clob_order_id", sa.String(128), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("placed_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved", sa.Boolean, default=False),
        sa.Column("pnl", sa.Float, nullable=True),
    )
    op.create_index("ix_bets_run_id", "bets", ["pipeline_run_id"])
    op.create_index("ix_bets_market_id", "bets", ["market_id"])

    # --- settings ---
    op.create_table(
        "settings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("value", JSONB, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("category", "key", name="uq_settings_category_key"),
    )
    op.create_index("ix_settings_category", "settings", ["category"])

    # --- prompt_templates ---
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(64), unique=True, nullable=False),
        sa.Column("template", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_prompt_templates_name", "prompt_templates", ["name"])


def downgrade() -> None:
    op.drop_table("bets")
    op.drop_table("decisions")
    op.drop_table("analyses")
    op.drop_table("llm_calls")
    op.drop_table("market_snapshots")
    op.drop_table("markets")
    op.drop_table("pipeline_runs")
    op.drop_table("settings")
    op.drop_table("prompt_templates")
    op.execute("DROP TYPE IF EXISTS pipeline_status")
    op.execute("DROP TYPE IF EXISTS pipeline_trigger")
    op.execute("DROP TYPE IF EXISTS pipeline_mode")
    op.execute("DROP TYPE IF EXISTS decision_action")
    op.execute("DROP TYPE IF EXISTS bet_side")
    op.execute("DROP TYPE IF EXISTS bet_mode")
    op.execute("DROP TYPE IF EXISTS bet_status")
