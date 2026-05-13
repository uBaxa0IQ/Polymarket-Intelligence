from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.execution_order import ExecutionOrder


class BetExecutionEvent(Base):
    """Append-only event log for decisions, funds, and exchange execution."""

    __tablename__ = "bet_execution_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    pipeline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    decision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("decisions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    bet_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    execution_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("execution_orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    client_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    exchange_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    stage: Mapped[str] = mapped_column(
        Enum(
            "decision",
            "risk",
            "reservation",
            "submit",
            "execution",
            "reconcile",
            "settlement",
            "system",
            name="bet_event_stage",
        ),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(
        Enum("debug", "info", "warn", "error", "critical", name="bet_event_severity"),
        default="info",
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(256), nullable=True, unique=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=lambda: {})

    execution_order: Mapped["ExecutionOrder | None"] = relationship("ExecutionOrder", back_populates="events")
