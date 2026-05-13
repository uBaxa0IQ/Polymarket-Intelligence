from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.bet_execution_event import BetExecutionEvent
    from app.models.funds_ledger import FundsLedgerEntry


class ExecutionOrder(Base):
    """Pre-exchange draft / live order state. client_order_id is unique (idempotency)."""

    __tablename__ = "execution_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), index=True
    )
    decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("decisions.id", ondelete="CASCADE"), index=True
    )
    bet_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    market_id: Mapped[str] = mapped_column(String(64), ForeignKey("markets.market_id", ondelete="RESTRICT"), index=True)
    condition_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    side: Mapped[str] = mapped_column(Enum("yes", "no", name="bet_side"), nullable=False)
    intent_amount_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    intent_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    intent_shares: Mapped[float | None] = mapped_column(Float, nullable=True)
    client_order_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    exchange_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        Enum(
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
        ),
        nullable=False,
    )
    last_exchange_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    submit_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    reserved_amount_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    ledger_entries: Mapped[list["FundsLedgerEntry"]] = relationship(
        "FundsLedgerEntry", back_populates="execution_order"
    )
    events: Mapped[list["BetExecutionEvent"]] = relationship("BetExecutionEvent", back_populates="execution_order")
