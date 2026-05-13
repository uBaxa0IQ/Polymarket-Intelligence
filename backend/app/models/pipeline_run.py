from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("pending", "running", "completed", "failed", "cancelled", name="pipeline_status"),
        default="pending",
    )
    trigger: Mapped[str] = mapped_column(
        Enum("manual", "scheduled", name="pipeline_trigger"),
        default="manual",
    )
    config_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    screener_results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ranker_results: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    current_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    markets_screened: Mapped[int] = mapped_column(Integer, default=0)
    markets_ranked: Mapped[int] = mapped_column(Integer, default=0)
    markets_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    decisions_count: Mapped[int] = mapped_column(Integer, default=0)
    bets_placed: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    llm_calls: Mapped[list] = relationship("LLMCall", back_populates="pipeline_run", lazy="select")
    analyses: Mapped[list] = relationship("Analysis", back_populates="pipeline_run", lazy="select")
    decisions: Mapped[list] = relationship("Decision", back_populates="pipeline_run", lazy="select")
    bets: Mapped[list] = relationship("Bet", back_populates="pipeline_run", lazy="select")
    market_snapshots: Mapped[list] = relationship("MarketSnapshot", back_populates="pipeline_run", lazy="select")
