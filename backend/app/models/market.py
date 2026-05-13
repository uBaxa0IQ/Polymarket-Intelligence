from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Market(Base):
    __tablename__ = "markets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    condition_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    market_slug: Mapped[str | None] = mapped_column(String(256), nullable=True)
    event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    snapshots: Mapped[list] = relationship("MarketSnapshot", back_populates="market", lazy="select")
    analyses: Mapped[list] = relationship("Analysis", back_populates="market", lazy="select")
    llm_calls: Mapped[list] = relationship("LLMCall", back_populates="market", lazy="select")


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market_id: Mapped[str] = mapped_column(String(64), ForeignKey("markets.market_id"), nullable=False, index=True)
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    yes_implied: Mapped[float | None] = mapped_column(Float, nullable=True)
    no_implied: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    hours_left: Mapped[float | None] = mapped_column(Float, nullable=True)

    market: Mapped[Market] = relationship("Market", back_populates="snapshots")
    pipeline_run: Mapped["PipelineRun"] = relationship("PipelineRun", back_populates="market_snapshots")
