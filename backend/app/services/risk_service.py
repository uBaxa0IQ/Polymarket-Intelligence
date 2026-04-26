"""Pre-trade risk: kill switch, daily loss, per-market exposure."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bet import Bet


def _as_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        s = value.strip().lower()
        if s in {"true", "1", "yes", "on"}:
            return True
        if s in {"false", "0", "no", "off"}:
            return False
    if value is None:
        return default
    return bool(value)


class RiskService:
    def kill_switch(self, config: dict) -> bool:
        r = config.get("risk") or {}
        return _as_bool(r.get("execution_kill_switch", False), default=False)

    def daily_loss_limit(self, config: dict) -> float | None:
        r = config.get("risk") or {}
        v = r.get("daily_loss_limit_usd")
        if v is None:
            return None
        try:
            return float(v) if float(v) > 0 else None
        except (TypeError, ValueError):
            return None

    def max_exposure_per_market(self, config: dict) -> float | None:
        r = config.get("risk") or {}
        v = r.get("max_exposure_per_market_usd")
        if v is None:
            return None
        try:
            return float(v) if float(v) > 0 else None
        except (TypeError, ValueError):
            return None

    async def todays_loss_magnitude_usd(self, db: AsyncSession) -> float:
        """How much (positive USD) was lost on resolved negative-P&L bets today, UTC day."""
        start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        q = select(func.coalesce(func.sum(Bet.pnl), 0.0)).where(
            Bet.resolved == True,  # noqa: E712
            Bet.pnl < 0,
            Bet.status != "dry_run",
            Bet.resolved_at >= start,
        )
        s = float((await db.execute(q)).scalar() or 0.0)
        return -s if s < 0 else 0.0

    async def open_exposure_market_usd(
        self, db: AsyncSession, market_id: str
    ) -> float:
        q = select(func.coalesce(func.sum(Bet.amount_usd), 0.0)).where(
            Bet.market_id == market_id,
            Bet.status != "dry_run",
            Bet.status.in_(("pending", "partial")),
        )
        return float((await db.execute(q)).scalar() or 0.0)

    async def check_can_place(
        self,
        db: AsyncSession,
        config: dict,
        *,
        market_id: str,
        notional_usd: float,
    ) -> tuple[bool, str | None]:
        if self.kill_switch(config):
            return False, "execution_kill_switch"
        dlim = self.daily_loss_limit(config)
        if dlim is not None:
            lost = await self.todays_loss_magnitude_usd(db)
            if lost + 1e-9 >= dlim:
                return False, "daily_loss_limit"
        exp_cap = self.max_exposure_per_market(config)
        if exp_cap is not None:
            cur = await self.open_exposure_market_usd(db, market_id)
            if cur + notional_usd > exp_cap + 1e-6:
                return False, "per_market_exposure_cap"
        return True, None


risk_service = RiskService()
