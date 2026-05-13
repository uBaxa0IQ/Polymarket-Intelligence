from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Bet(Base):
    __tablename__ = "bets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    decision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("decisions.id"), nullable=False)
    execution_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("execution_orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=False, index=True)
    market_id: Mapped[str] = mapped_column(String(64), ForeignKey("markets.market_id"), nullable=False, index=True)
    condition_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    side: Mapped[str] = mapped_column(Enum("yes", "no", name="bet_side"), nullable=False)
    source: Mapped[str] = mapped_column(
        Enum("pipeline", "copytrading", name="bet_source"),
        nullable=False,
        default="pipeline",
        server_default="pipeline",
    )
    amount_usd: Mapped[float] = mapped_column(Float, nullable=False)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    shares: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("pending", "filled", "partial", "failed", "cancelled", "dry_run", name="bet_status"),
        default="pending",
    )
    clob_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    fee_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    decision: Mapped["Decision"] = relationship("Decision", back_populates="bet")
    execution_order: Mapped["ExecutionOrder | None"] = relationship(
        "ExecutionOrder", foreign_keys=[execution_order_id]
    )
    pipeline_run: Mapped["PipelineRun"] = relationship("PipelineRun", back_populates="bets")
