from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:
    from app.models.execution_order import ExecutionOrder


class FundsLedgerEntry(Base):
    __tablename__ = "funds_ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    wallet_scope: Mapped[str] = mapped_column(
        String(32), ForeignKey("wallet_state.wallet_scope", ondelete="RESTRICT"), index=True
    )
    entry_type: Mapped[str] = mapped_column(
        Enum(
            "snapshot",
            "reserve",
            "release",
            "fill_debit",
            "fill_credit",
            "fee_debit",
            "manual_adjustment",
            name="funds_entry_type",
        ),
        nullable=False,
    )
    amount_usd: Mapped[float] = mapped_column(Float, nullable=False)
    available_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    locked_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    execution_order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("execution_orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(256), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    execution_order: Mapped["ExecutionOrder | None"] = relationship(
        "ExecutionOrder", back_populates="ledger_entries"
    )
