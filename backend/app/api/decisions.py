from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.auth import get_current_user
from app.database import get_db
from app.models.decision import Decision
from app.models.market import Market
from app.models.pipeline_run import PipelineRun

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("")
async def list_decisions(
    action: str | None = Query(None),
    run_id: uuid.UUID | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    q = (
        select(Decision, Market.question, PipelineRun.trigger)
        .join(PipelineRun, PipelineRun.id == Decision.pipeline_run_id)
        .outerjoin(Market, Market.market_id == Decision.market_id)
        .order_by(desc(Decision.created_at))
    )
    if action:
        q = q.where(Decision.action == action)
    if run_id:
        q = q.where(Decision.pipeline_run_id == run_id)
    result = await db.execute(q.offset(offset).limit(limit))
    rows = result.all()
    return [
        {
            "id": str(d.id),
            "pipeline_run_id": str(d.pipeline_run_id),
            "run_trigger": trigger,
            "market_id": d.market_id,
            "question": question,
            "action": d.action,
            "reason": d.reason,
            "kelly_fraction": d.kelly_fraction,
            "bet_size_usd": d.bet_size_usd,
            "p_yes": d.p_yes,
            "p_market": d.p_market,
            "gap": d.gap,
            "confidence": d.confidence,
            "bankroll_usd": d.bankroll_usd,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d, question, trigger in rows
    ]
