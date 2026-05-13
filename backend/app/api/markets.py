from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.auth import get_current_user
from app.database import get_db
from app.models.market import Market, MarketSnapshot

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("")
async def list_markets(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Market).order_by(desc(Market.last_seen_at)).offset(offset).limit(limit)
    )
    markets = result.scalars().all()
    return [
        {
            "market_id": m.market_id,
            "question": m.question,
            "market_slug": m.market_slug,
            "tags": m.tags,
            "end_date": m.end_date.isoformat() if m.end_date else None,
            "first_seen_at": m.first_seen_at.isoformat() if m.first_seen_at else None,
            "last_seen_at": m.last_seen_at.isoformat() if m.last_seen_at else None,
        }
        for m in markets
    ]


@router.get("/{market_id}")
async def get_market(market_id: str, db: AsyncSession = Depends(get_db)):
    from fastapi import HTTPException
    from app.models.analysis import Analysis
    result = await db.execute(select(Market).where(Market.market_id == market_id))
    m = result.scalar_one_or_none()
    if m is None:
        raise HTTPException(404, "Market not found")

    analyses_result = await db.execute(
        select(Analysis).where(Analysis.market_id == market_id).order_by(desc(Analysis.created_at)).limit(20)
    )
    analyses = analyses_result.scalars().all()

    return {
        "market_id": m.market_id,
        "question": m.question,
        "market_slug": m.market_slug,
        "condition_id": m.condition_id,
        "event_title": m.event_title,
        "tags": m.tags,
        "end_date": m.end_date.isoformat() if m.end_date else None,
        "analyses": [
            {
                "id": str(a.id),
                "pipeline_run_id": str(a.pipeline_run_id),
                "p_yes": a.p_yes,
                "confidence": a.confidence,
                "p_market": a.p_market,
                "gap": a.gap,
                "research_priority": a.research_priority,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in analyses
        ],
    }


@router.get("/{market_id}/snapshots")
async def get_market_snapshots(
    market_id: str,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(MarketSnapshot)
        .where(MarketSnapshot.market_id == market_id)
        .order_by(desc(MarketSnapshot.captured_at))
        .limit(limit)
    )
    snaps = result.scalars().all()
    return [
        {
            "captured_at": s.captured_at.isoformat() if s.captured_at else None,
            "yes_implied": s.yes_implied,
            "no_implied": s.no_implied,
            "volume": s.volume,
            "hours_left": s.hours_left,
        }
        for s in snaps
    ]
