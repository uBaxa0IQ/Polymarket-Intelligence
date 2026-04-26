"""execution_orders, bet_execution_events, wallet_state, funds_ledger; decision_trace.

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-23
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM, JSONB, UUID

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def _create_pg_enum_if_not_exists(name: str, values: tuple[str, ...]) -> None:
    literal = ", ".join(repr(v) for v in values)
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            f"CREATE TYPE {name} AS ENUM ({literal}); "
            "EXCEPTION WHEN duplicate_object THEN NULL; END $$;"
        )
    )


def upgrade() -> None:
    _create_pg_enum_if_not_exists(
        "execution_order_status",
        (
            "draft",
            "submit_pending",
            "submitted",
            "partially_filled",
            "filled",
            "cancel_pending",
            "cancelled",
            "rejected",
            "failed",
            "orphaned",
        ),
    )
    _create_pg_enum_if_not_exists(
        "bet_event_stage",
        ("decision", "risk", "reservation", "submit", "execution", "reconcile", "settlement", "system"),
    )
    _create_pg_enum_if_not_exists(
        "bet_event_severity", ("debug", "info", "warn", "error", "critical")
    )
    _create_pg_enum_if_not_exists(
        "funds_entry_type",
        ("snapshot", "reserve", "release", "fill_debit", "fill_credit", "fee_debit", "manual_adjustment"),
    )

    # --- wallet_state (single row per scope, locked via SELECT FOR UPDATE) ---
    op.create_table(
        "wallet_state",
        sa.Column("wallet_scope", sa.String(32), primary_key=True),
        sa.Column("available_usd", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("locked_usd", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.execute(
        sa.text(
            "INSERT INTO wallet_state (wallet_scope, available_usd, locked_usd) "
            "VALUES ('main', 0, 0) ON CONFLICT (wallet_scope) DO NOTHING"
        )
    )

    # --- decision_trace ---
    op.add_column("decisions", sa.Column("decision_trace", JSONB, nullable=True))

    # --- execution_orders ---
    op.create_table(
        "execution_orders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("pipeline_run_id", UUID(as_uuid=True), sa.ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("decision_id", UUID(as_uuid=True), sa.ForeignKey("decisions.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("bet_id", UUID(as_uuid=True), sa.ForeignKey("bets.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("market_id", sa.String(64), sa.ForeignKey("markets.market_id", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column("condition_id", sa.String(128), nullable=True),
        sa.Column("side", PG_ENUM("yes", "no", name="bet_side", create_type=False), nullable=False),
        sa.Column("intent_amount_usd", sa.Float(), nullable=True),
        sa.Column("intent_price", sa.Float(), nullable=True),
        sa.Column("intent_shares", sa.Float(), nullable=True),
        sa.Column("client_order_id", sa.String(128), nullable=False),
        sa.Column("exchange_order_id", sa.String(128), nullable=True),
        sa.Column(
            "status",
            PG_ENUM(
                "draft",
                "submit_pending",
                "submitted",
                "partially_filled",
                "filled",
                "cancel_pending",
                "cancelled",
                "rejected",
                "failed",
                "orphaned",
                name="execution_order_status",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("last_exchange_status", sa.Text(), nullable=True),
        sa.Column("submit_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("client_order_id", name="uq_execution_orders_client_order_id"),
    )
    op.create_index("ix_execution_orders_status_updated", "execution_orders", ["status", "updated_at"])
    op.create_index("ix_execution_orders_exchange_order_id", "execution_orders", ["exchange_order_id"])

    # --- funds_ledger ---
    op.create_table(
        "funds_ledger",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("wallet_scope", sa.String(32), sa.ForeignKey("wallet_state.wallet_scope", ondelete="RESTRICT"), nullable=False, index=True),
        sa.Column(
            "entry_type",
            PG_ENUM(
                "snapshot",
                "reserve",
                "release",
                "fill_debit",
                "fill_credit",
                "fee_debit",
                "manual_adjustment",
                name="funds_entry_type",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("amount_usd", sa.Float(), nullable=False),
        sa.Column("available_after", sa.Float(), nullable=True),
        sa.Column("locked_after", sa.Float(), nullable=True),
        sa.Column("execution_order_id", UUID(as_uuid=True), sa.ForeignKey("execution_orders.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(256), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_funds_ledger_created_at", "funds_ledger", ["created_at"])
    op.create_unique_constraint("uq_funds_ledger_idempotency_key", "funds_ledger", ["idempotency_key"])

    # --- bet_execution_events (immutable append-only) ---
    op.create_table(
        "bet_execution_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("event_time", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, index=True),
        sa.Column("pipeline_run_id", UUID(as_uuid=True), sa.ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=True, index=True),
        sa.Column("decision_id", UUID(as_uuid=True), sa.ForeignKey("decisions.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("bet_id", UUID(as_uuid=True), sa.ForeignKey("bets.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("execution_order_id", UUID(as_uuid=True), sa.ForeignKey("execution_orders.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("client_order_id", sa.String(128), nullable=True, index=True),
        sa.Column("exchange_order_id", sa.String(128), nullable=True, index=True),
        sa.Column(
            "stage",
            PG_ENUM(
                "decision",
                "risk",
                "reservation",
                "submit",
                "execution",
                "reconcile",
                "settlement",
                "system",
                name="bet_event_stage",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column(
            "severity",
            PG_ENUM("debug", "info", "warn", "error", "critical", name="bet_event_severity", create_type=False),
            nullable=False,
            server_default="info",
        ),
        sa.Column("idempotency_key", sa.String(256), nullable=True),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_bet_execution_events_run_time", "bet_execution_events", ["pipeline_run_id", "event_time"])
    op.create_unique_constraint("uq_bet_execution_events_idempotency", "bet_execution_events", ["idempotency_key"])


def downgrade() -> None:
    op.drop_index("ix_bet_execution_events_run_time", table_name="bet_execution_events")
    op.drop_constraint("uq_bet_execution_events_idempotency", "bet_execution_events", type_="unique")
    op.drop_table("bet_execution_events")

    op.drop_constraint("uq_funds_ledger_idempotency_key", "funds_ledger", type_="unique")
    op.drop_index("ix_funds_ledger_created_at", table_name="funds_ledger")
    op.drop_table("funds_ledger")

    op.drop_index("ix_execution_orders_exchange_order_id", table_name="execution_orders")
    op.drop_index("ix_execution_orders_status_updated", table_name="execution_orders")
    op.drop_table("execution_orders")

    op.drop_column("decisions", "decision_trace")

    op.drop_table("wallet_state")

    op.execute("DROP TYPE IF EXISTS funds_entry_type")
    op.execute("DROP TYPE IF EXISTS bet_event_severity")
    op.execute("DROP TYPE IF EXISTS bet_event_stage")
    op.execute("DROP TYPE IF EXISTS execution_order_status")
