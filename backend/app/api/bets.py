from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import desc, nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.auth import get_current_user
from app.database import get_db
from app.models.bet import Bet
from app.models.decision import Decision
from app.models.market import Market

router = APIRouter(dependencies=[Depends(get_current_user)])


class ResolveRequest(BaseModel):
    pnl: float


@router.get("")
async def list_bets(
    status: str | None = Query(None),
    resolved: bool | None = Query(None, description="If set, filter by Bet.resolved"),
    exclude_dry_run: bool = Query(False, description="If true, omit dry_run rows"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(Bet)
        .join(Market, Market.market_id == Bet.market_id)
        .order_by(nulls_last(desc(Market.end_date)), desc(Bet.placed_at))
    )
    if status:
        q = q.where(Bet.status == status)
    if resolved is not None:
        q = q.where(Bet.resolved == resolved)
    if exclude_dry_run:
        q = q.where(Bet.status != "dry_run")
    result = await db.execute(q.offset(offset).limit(limit))
    bets = result.scalars().all()
    return await _bets_to_dicts(db, bets)


@router.post("/sync-settlements")
async def sync_settlements(db: AsyncSession = Depends(get_db)):
    """Resolve open bets from Gamma (closed markets + outcomePrices) and compute P&L."""
    from app.services.settings_service import settings_service
    from app.services.bet_settlement_service import bet_settlement_service

    cfg = await settings_service.get_all_as_dict(db)
    return await bet_settlement_service.sync_unresolved(config=cfg)


@router.get("/{bet_id}/stream")
async def stream_bet_status(bet_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """SSE stream — emits bet status updates until filled/failed/resolved or 6-minute timeout."""
    result = await db.execute(select(Bet).where(Bet.id == bet_id))
    b = result.scalar_one_or_none()
    if b is None:
        raise HTTPException(404, "Bet not found")

    async def event_generator():
        from app.database import async_session_factory
        deadline = asyncio.get_event_loop().time() + 360  # 6 min max
        poll_secs = 5

        while asyncio.get_event_loop().time() < deadline:
            async with async_session_factory() as session:
                res = await session.execute(select(Bet).where(Bet.id == bet_id))
                row = res.scalar_one_or_none()

            if row is None:
                yield _sse({"error": "bet not found"})
                return

            payload = {
                "id": str(row.id),
                "status": row.status,
                "shares": row.shares,
                "price": row.price,
                "fee_usd": row.fee_usd,
                "filled_at": row.filled_at.isoformat() if row.filled_at else None,
                "resolved": row.resolved,
                "pnl": row.pnl,
            }
            yield _sse(payload)

            if row.status in ("filled", "failed", "cancelled") or row.resolved:
                return

            await asyncio.sleep(poll_secs)

        yield _sse({"timeout": True})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/{bet_id}")
async def get_bet(bet_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Bet).where(Bet.id == bet_id))
    b = result.scalar_one_or_none()
    if b is None:
        raise HTTPException(404, "Bet not found")
    return await _bet_to_single_dict(db, b)


@router.post("/{bet_id}/retry", status_code=200)
async def retry_bet(bet_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Re-place a failed bet using the original Decision parameters. Price is fetched live from CLOB."""
    from app.services.betting_service import betting_service
    from app.services.settings_service import settings_service

    result = await db.execute(select(Bet).where(Bet.id == bet_id))
    b = result.scalar_one_or_none()
    if b is None:
        raise HTTPException(404, "Bet not found")
    if b.status != "failed":
        raise HTTPException(400, f"Only failed bets can be retried (current status: '{b.status}')")

    dec_res = await db.execute(select(Decision).where(Decision.id == b.decision_id))
    decision = dec_res.scalar_one_or_none()
    if decision is None:
        raise HTTPException(404, "Decision not found")
    if not decision.bet_size_usd or decision.bet_size_usd <= 0:
        raise HTTPException(400, "Decision has no valid bet size")
    if not b.condition_id:
        raise HTTPException(400, "Bet has no condition_id — cannot submit to CLOB")

    cfg = await settings_service.get_all_as_dict(db)
    theoretical_price = decision.p_market or b.price or 0.5

    new_bet_id = await betting_service.place_bet(
        decision_id=str(decision.id),
        pipeline_run_id=str(b.pipeline_run_id),
        market_id=b.market_id,
        condition_id=b.condition_id,
        side=b.side,
        amount_usd=decision.bet_size_usd,
        theoretical_price=theoretical_price,
        config=cfg,
        source=b.source or "pipeline",
    )
    if new_bet_id is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not place a new bet (risk limits, missing CLOB credentials or py-clob-client, "
                "invalid order_time_in_force, missing condition_id, insufficient funds, or order error)"
            ),
        )

    new_res = await db.execute(select(Bet).where(Bet.id == uuid.UUID(new_bet_id)))
    new_bet = new_res.scalar_one_or_none()
    if new_bet is None:
        return {"bet_id": new_bet_id}
    return await _bet_to_single_dict(db, new_bet)


@router.post("/{bet_id}/resolve", status_code=200)
async def resolve_bet(bet_id: uuid.UUID, body: ResolveRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Bet).where(Bet.id == bet_id))
    b = result.scalar_one_or_none()
    if b is None:
        raise HTTPException(404, "Bet not found")
    b.resolved = True
    b.pnl = body.pnl
    b.resolved_at = datetime.now(timezone.utc)
    b.resolution_source = "manual"
    await db.commit()
    return await _bet_to_single_dict(db, b)


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


def _polymarket_market_url(market_slug: str | None) -> str | None:
    if not market_slug or not str(market_slug).strip():
        return None
    s = str(market_slug).strip()
    return f"https://polymarket.com/market/{quote(s, safe='/-_.~')}"


def _bet_to_dict(
    b: Bet,
    market_slug: str | None = None,
    market_end_date: datetime | None = None,
    decision: Decision | None = None,
) -> dict:
    slug = market_slug if market_slug and str(market_slug).strip() else None
    out: dict = {
        "id": str(b.id),
        "decision_id": str(b.decision_id),
        "pipeline_run_id": str(b.pipeline_run_id),
        "market_id": b.market_id,
        "source": b.source,
        "market_slug": slug,
        "market_end_date": market_end_date.isoformat() if market_end_date else None,
        "polymarket_url": _polymarket_market_url(slug),
        "condition_id": b.condition_id,
        "side": b.side,
        "amount_usd": b.amount_usd,
        "price": b.price,
        "shares": b.shares,
        "fee_usd": b.fee_usd,
        "status": b.status,
        "clob_order_id": b.clob_order_id,
        "error_message": b.error_message,
        "placed_at": b.placed_at.isoformat() if b.placed_at else None,
        "filled_at": b.filled_at.isoformat() if b.filled_at else None,
        "resolved": b.resolved,
        "resolved_at": b.resolved_at.isoformat() if b.resolved_at else None,
        "resolution_source": b.resolution_source,
        "pnl": b.pnl,
    }
    if decision is not None:
        out["p_yes"] = decision.p_yes
        out["p_market"] = decision.p_market
        out["gap"] = decision.gap
        out["confidence"] = decision.confidence
        out["reason"] = decision.reason
    return out


async def _decisions_by_ids(db: AsyncSession, decision_ids: list[uuid.UUID]) -> dict[str, Decision]:
    if not decision_ids:
        return {}
    res = await db.execute(select(Decision).where(Decision.id.in_(decision_ids)))
    rows = res.scalars().all()
    return {str(d.id): d for d in rows}


async def _bets_to_dicts(db: AsyncSession, bets: list[Bet]) -> list[dict]:
    if not bets:
        return []
    market_ids = list({b.market_id for b in bets})
    res = await db.execute(
        select(Market.market_id, Market.market_slug, Market.end_date).where(Market.market_id.in_(market_ids))
    )
    market_by_id = {mid: {"slug": mslug, "end_date": end_date} for mid, mslug, end_date in res.all()}
    dec_map = await _decisions_by_ids(db, [b.decision_id for b in bets])
    return [
        _bet_to_dict(
            b,
            market_slug=market_by_id.get(b.market_id, {}).get("slug"),
            market_end_date=market_by_id.get(b.market_id, {}).get("end_date"),
            decision=dec_map.get(str(b.decision_id)),
        )
        for b in bets
    ]


async def _bet_to_single_dict(db: AsyncSession, b: Bet) -> dict:
    res = await db.execute(select(Market.market_slug, Market.end_date).where(Market.market_id == b.market_id))
    market_data = res.one_or_none()
    slug = market_data[0] if market_data else None
    end_date = market_data[1] if market_data else None
    dec_res = await db.execute(select(Decision).where(Decision.id == b.decision_id))
    decision = dec_res.scalar_one_or_none()
    return _bet_to_dict(b, market_slug=slug, market_end_date=end_date, decision=decision)
