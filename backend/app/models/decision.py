from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=False, index=True)
    analysis_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("analyses.id"), nullable=False)
    market_id: Mapped[str] = mapped_column(String(64), ForeignKey("markets.market_id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(
        Enum("bet_yes", "bet_no", "skip", name="decision_action"),
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    kelly_fraction: Mapped[float | None] = mapped_column(Float, nullable=True)
    bet_size_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    p_yes: Mapped[float | None] = mapped_column(Float, nullable=True)
    p_market: Mapped[float | None] = mapped_column(Float, nullable=True)
    gap: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    bankroll_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Kelly inputs, thresholds, exchange constraints — filled as stages 2+ land.
    decision_trace: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    pipeline_run: Mapped["PipelineRun"] = relationship("PipelineRun", back_populates="decisions")
    analysis: Mapped["Analysis"] = relationship("Analysis", back_populates="decision")
    bet: Mapped["Bet | None"] = relationship("Bet", back_populates="decision", uselist=False)
