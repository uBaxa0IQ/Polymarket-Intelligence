"""Stage 4: place bets from decisions."""
from __future__ import annotations

import logging
import uuid

from app.graph.pipeline_persistence import raise_if_pipeline_cancelled, update_pipeline_run
from app.graph.state import PipelineState

logger = logging.getLogger(__name__)

async def execute_bets(state: PipelineState) -> dict:
    from app.models.decision import Decision
    from app.models.market import Market
    from app.database import async_session_factory
    from app.services.betting_service import betting_service
    from sqlalchemy import select

    pipeline_run_id = uuid.UUID(state["pipeline_run_id"])
    config = state["config"]
    await raise_if_pipeline_cancelled(str(pipeline_run_id))
    await update_pipeline_run(state["pipeline_run_id"], current_stage="executor")

    async with async_session_factory() as db:
        result = await db.execute(
            select(Decision).where(
                Decision.pipeline_run_id == pipeline_run_id,
                Decision.action.in_(["bet_yes", "bet_no"]),
            )
        )
        decisions = result.scalars().all()

    bets_placed = 0
    for decision in decisions:
        await raise_if_pipeline_cancelled(str(pipeline_run_id))
        side = "yes" if decision.action == "bet_yes" else "no"
        price = decision.p_market if side == "yes" else (1.0 - (decision.p_market or 0.5))

        async with async_session_factory() as db:
            res = await db.execute(select(Market).where(Market.market_id == decision.market_id))
            m = res.scalar_one_or_none()
            condition_id = m.condition_id if m else None

        bet_id = await betting_service.place_bet(
            decision_id=str(decision.id),
            pipeline_run_id=str(pipeline_run_id),
            market_id=decision.market_id,
            condition_id=condition_id,
            side=side,
            amount_usd=decision.bet_size_usd or 0,
            theoretical_price=price,
            config=config,
        )
        if bet_id is not None:
            bets_placed += 1

    await update_pipeline_run(state["pipeline_run_id"], bets_placed=bets_placed)
    return {}
