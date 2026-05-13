from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class WalletSnapshot(Base):
    __tablename__ = "wallet_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    wallet_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    collateral_balance_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    positions_value_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    open_positions_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
