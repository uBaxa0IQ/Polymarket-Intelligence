"""Auto-resolve bets from closed Gamma markets + computed P&L."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import async_session_factory
from app.models.bet import Bet

logger = logging.getLogger(__name__)


def _gamma_root_from_config(config: dict | None) -> str:
    if not config:
        return "https://gamma-api.polymarket.com"
    base = (config.get("screener") or {}).get("gamma_api_base") or "https://gamma-api.polymarket.com/events"
    s = str(base).strip()
    if "/events" in s:
        s = s.split("/events")[0]
    return s.rstrip("/") or "https://gamma-api.polymarket.com"


class BetSettlementService:
    async def sync_unresolved(self, *, config: dict | None = None, limit: int = 300) -> dict[str, int | list]:
        from app.integrations.polymarket.gamma_markets import fetch_gamma_market_by_id
        from app.domain.betting.settlement_math import settlement_pnl_usd, winner_yes_no_from_gamma

        cfg = config or {}
        gamma_host = _gamma_root_from_config(cfg)

        async with async_session_factory() as db:
            result = await db.execute(
                select(Bet)
                .where(Bet.resolved.is_(False))
                .where(Bet.status.in_(("filled", "partial")))
                .order_by(Bet.placed_at.desc())
                .limit(limit)
            )
            bets: list[Bet] = list(result.scalars().all())

        checked = settled = skipped = errors = 0
        details: list[str] = []

        for bet in bets:
            checked += 1
            mid = str(bet.market_id).strip()
            if not mid:
                skipped += 1
                continue

            try:
                mkt = await asyncio.to_thread(
                    fetch_gamma_market_by_id,
                    mid,
                    base_url=gamma_host,
                )
            except Exception as exc:
                errors += 1
                details.append(f"{bet.id}: fetch error {exc}")
                continue

            if not mkt:
                skipped += 1
                details.append(f"{bet.id}: no gamma data")
                continue

            winner = winner_yes_no_from_gamma(mkt)
            if winner is None:
                skipped += 1
                continue

            pnl = settlement_pnl_usd(
                side=bet.side,
                amount_usd=float(bet.amount_usd or 0),
                shares=bet.shares,
                winner=winner,
                fee_usd=bet.fee_usd,
            )
            if pnl is None:
                skipped += 1
                details.append(f"{bet.id}: pnl calc skip")
                continue

            resolved_at = datetime.now(timezone.utc)
            async with async_session_factory() as db2:
                row = await db2.get(Bet, bet.id)
                if row is None or row.resolved:
                    continue
                row.resolved = True
                row.pnl = pnl
                row.resolved_at = resolved_at
                row.resolution_source = "gamma"
                await db2.commit()
            settled += 1

            # Index into Qdrant for future RAG lookups
            try:
                from app.services.qdrant_service import qdrant_service
                from app.integrations.polymarket.gamma_markets import fetch_gamma_market_by_id
                question = str(mkt.get("question") or mkt.get("title") or mid)
                # Fetch p_yes from analysis if available
                from sqlalchemy import select as sa_select
                from app.models.analysis import Analysis
                async with async_session_factory() as db3:
                    res = await db3.execute(
                        sa_select(Analysis.p_yes)
                        .where(Analysis.market_id == mid)
                        .order_by(Analysis.created_at.desc())
                        .limit(1)
                    )
                    p_yes_row = res.scalar_one_or_none()
                await qdrant_service.upsert_resolved_market(
                    market_id=mid,
                    question=question,
                    outcome=winner,
                    p_market=float(mkt.get("lastTradePrice") or bet.price or 0),
                    p_yes_estimated=float(p_yes_row) if p_yes_row is not None else None,
                    pnl=pnl,
                    resolved_at=resolved_at.isoformat(),
                )
            except Exception as exc:
                logger.warning("Qdrant index failed for %s: %s", mid, exc)

        return {
            "checked": checked,
            "settled": settled,
            "skipped": skipped,
            "errors": errors,
            "details": details[:50],
        }


bet_settlement_service = BetSettlementService()
