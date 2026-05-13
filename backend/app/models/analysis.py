from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=False, index=True)
    market_id: Mapped[str] = mapped_column(String(64), ForeignKey("markets.market_id"), nullable=False, index=True)
    research_priority: Mapped[str | None] = mapped_column(String(16), nullable=True)
    structural_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_pool: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    p_yes: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    p_market: Mapped[float | None] = mapped_column(Float, nullable=True)
    gap: Mapped[float | None] = mapped_column(Float, nullable=True)
    debate_pairs_completed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    debate_consensus: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    debate_stop_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    debate_history: Mapped[list | dict | None] = mapped_column(JSONB, nullable=True)
    failed_stages: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    pipeline_run: Mapped["PipelineRun"] = relationship("PipelineRun", back_populates="analyses")
    market: Mapped["Market"] = relationship("Market", back_populates="analyses")
    decision: Mapped["Decision | None"] = relationship("Decision", back_populates="analysis", uselist=False)
