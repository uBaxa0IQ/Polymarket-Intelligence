from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class WalletState(Base):
    """Authoritative in-app balance: available vs reserved (locked) USD per scope.

    Mutations must be serialized via SELECT ... FOR UPDATE in FundsService.
    """

    __tablename__ = "wallet_state"

    wallet_scope: Mapped[str] = mapped_column(String(32), primary_key=True)
    available_usd: Mapped[float] = mapped_column(Float, default=0.0)
    locked_usd: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
