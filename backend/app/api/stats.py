"""Token usage and cost statistics."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.auth import get_current_user
from app.database import get_db
from app.models.llm_call import LLMCall
from app.models.pipeline_run import PipelineRun

router = APIRouter(dependencies=[Depends(get_current_user)])


def _period_start(period: str) -> datetime | None:
    now = datetime.now(timezone.utc)
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "7d":
        return now - timedelta(days=7)
    if period == "30d":
        return now - timedelta(days=30)
    return None  # all time


@router.get("/tokens")
async def token_stats(
    period: str = Query("today", pattern="^(today|7d|30d|all)$"),
    db: AsyncSession = Depends(get_db),
):
    since = _period_start(period)
    q = select(LLMCall)
    if since:
        q = q.where(LLMCall.created_at >= since)
    result = await db.execute(q)
    calls = result.scalars().all()

    by_stage: dict[str, dict] = {}
    by_model: dict[str, dict] = {}
    by_stage_model: dict[str, dict] = {}
    by_run: dict[str, dict] = {}
    by_retry_reason: dict[str, dict] = {}
    by_market: dict[str, dict] = {}

    total_input = total_output = total_cost = total_calls = retried_calls = 0
    total_duration_seconds = 0.0
    calls_with_duration = 0
    calls_with_errors = 0

    for c in calls:
        inp = c.input_tokens or 0
        out = c.output_tokens or 0
        cost = c.cost_usd or 0.0
        retried = 1 if (c.retry_count or 0) > 0 else 0
        duration = c.duration_seconds or 0.0
        has_error = bool(c.error)

        total_input += inp
        total_output += out
        total_cost += cost
        total_calls += 1
        retried_calls += retried
        if c.duration_seconds is not None:
            total_duration_seconds += duration
            calls_with_duration += 1
        if has_error:
            calls_with_errors += 1

        # By stage
        s = c.stage or "unknown"
        if s not in by_stage:
            by_stage[s] = {
                "stage": s,
                "calls": 0,
                "retried": 0,
                "errors": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "duration_seconds": 0.0,
            }
        by_stage[s]["calls"] += 1
        by_stage[s]["retried"] += retried
        by_stage[s]["errors"] += 1 if has_error else 0
        by_stage[s]["input_tokens"] += inp
        by_stage[s]["output_tokens"] += out
        by_stage[s]["cost_usd"] += cost
        by_stage[s]["duration_seconds"] += duration

        # By model
        mk = f"{c.provider}/{c.model}"
        if mk not in by_model:
            by_model[mk] = {
                "model": c.model,
                "provider": c.provider,
                "calls": 0,
                "retried": 0,
                "errors": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "duration_seconds": 0.0,
            }
        by_model[mk]["calls"] += 1
        by_model[mk]["retried"] += retried
        by_model[mk]["errors"] += 1 if has_error else 0
        by_model[mk]["input_tokens"] += inp
        by_model[mk]["output_tokens"] += out
        by_model[mk]["cost_usd"] += cost
        by_model[mk]["duration_seconds"] += duration

        # By stage + model (agent-level cost tracing)
        smk = f"{s}|{mk}"
        if smk not in by_stage_model:
            by_stage_model[smk] = {
                "stage": s,
                "provider": c.provider,
                "model": c.model,
                "calls": 0,
                "retried": 0,
                "errors": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "duration_seconds": 0.0,
            }
        by_stage_model[smk]["calls"] += 1
        by_stage_model[smk]["retried"] += retried
        by_stage_model[smk]["errors"] += 1 if has_error else 0
        by_stage_model[smk]["input_tokens"] += inp
        by_stage_model[smk]["output_tokens"] += out
        by_stage_model[smk]["cost_usd"] += cost
        by_stage_model[smk]["duration_seconds"] += duration

        # By run
        rid = str(c.pipeline_run_id)
        if rid not in by_run:
            by_run[rid] = {
                "run_id": rid,
                "calls": 0,
                "retried": 0,
                "errors": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "duration_seconds": 0.0,
                "started_at": None,
                "status": None,
            }
        by_run[rid]["calls"] += 1
        by_run[rid]["retried"] += retried
        by_run[rid]["errors"] += 1 if has_error else 0
        by_run[rid]["input_tokens"] += inp
        by_run[rid]["output_tokens"] += out
        by_run[rid]["cost_usd"] += cost
        by_run[rid]["duration_seconds"] += duration

        # Retry reason
        retry_reason = (c.retry_reason or "none").strip().lower()
        if retry_reason not in by_retry_reason:
            by_retry_reason[retry_reason] = {"retry_reason": retry_reason, "calls": 0}
        by_retry_reason[retry_reason]["calls"] += 1

        # By market
        market_id = c.market_id or "pipeline_level"
        if market_id not in by_market:
            by_market[market_id] = {
                "market_id": market_id,
                "calls": 0,
                "retried": 0,
                "errors": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "duration_seconds": 0.0,
            }
        by_market[market_id]["calls"] += 1
        by_market[market_id]["retried"] += retried
        by_market[market_id]["errors"] += 1 if has_error else 0
        by_market[market_id]["input_tokens"] += inp
        by_market[market_id]["output_tokens"] += out
        by_market[market_id]["cost_usd"] += cost
        by_market[market_id]["duration_seconds"] += duration

    # Attach run started_at
    if by_run:
        run_ids = list(by_run.keys())
        import uuid
        runs_result = await db.execute(
            select(PipelineRun.id, PipelineRun.started_at, PipelineRun.status).where(
                PipelineRun.id.in_([uuid.UUID(r) for r in run_ids])
            )
        )
        for rid, sat, status in runs_result.all():
            key = str(rid)
            if key in by_run:
                by_run[key]["started_at"] = sat.isoformat() if sat else None
                by_run[key]["status"] = status

    # Round costs
    for d in (
        list(by_stage.values())
        + list(by_model.values())
        + list(by_stage_model.values())
        + list(by_run.values())
        + list(by_market.values())
    ):
        d["cost_usd"] = round(d["cost_usd"], 6)
        d["duration_seconds"] = round(d["duration_seconds"], 3)
        d["avg_cost_per_call"] = round((d["cost_usd"] / d["calls"]) if d["calls"] else 0.0, 6)
        d["avg_duration_seconds"] = round((d["duration_seconds"] / d["calls"]) if d["calls"] else 0.0, 3)

    stage_order = ["ranker", "news", "baserate", "debate_bull_1", "debate_bear_1",
                   "debate_bull_2", "debate_bear_2", "judge"]

    def stage_sort(item):
        try:
            return stage_order.index(item["stage"])
        except ValueError:
            return 99

    return {
        "period": period,
        "by_stage": sorted(by_stage.values(), key=stage_sort),
        "by_model": sorted(by_model.values(), key=lambda x: -x["cost_usd"]),
        "by_stage_model": sorted(
            by_stage_model.values(),
            key=lambda x: (-x["cost_usd"], -x["calls"]),
        ),
        "by_retry_reason": sorted(by_retry_reason.values(), key=lambda x: -x["calls"]),
        "by_market": sorted(by_market.values(), key=lambda x: -x["cost_usd"])[:50],
        "by_run": sorted(by_run.values(), key=lambda x: x["started_at"] or "", reverse=True)[:20],
        "totals": {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cost_usd": round(total_cost, 6),
            "calls": total_calls,
            "retried_calls": retried_calls,
            "calls_with_errors": calls_with_errors,
            "duration_seconds": round(total_duration_seconds, 3),
            "avg_duration_seconds": round((total_duration_seconds / calls_with_duration) if calls_with_duration else 0.0, 3),
        },
    }


@router.post("/runtime-reset")
async def runtime_reset(db: AsyncSession = Depends(get_db)):
    active_run = await db.execute(
        select(PipelineRun.id).where(PipelineRun.status.in_(["pending", "running"])).limit(1)
    )
    if active_run.scalar_one_or_none() is not None:
        raise HTTPException(409, "Cannot reset runtime data while a pipeline run is active")

    from app.models.analysis import Analysis
    from app.models.bet import Bet
    from app.models.bet_execution_event import BetExecutionEvent
    from app.models.decision import Decision
    from app.models.execution_order import ExecutionOrder
    from app.models.funds_ledger import FundsLedgerEntry
    from app.models.llm_call import LLMCall
    from app.models.market import Market, MarketSnapshot
    from app.models.wallet_snapshot import WalletSnapshot
    from app.models.wallet_state import WalletState

    deleted = {}
    for model in (
        BetExecutionEvent,
        FundsLedgerEntry,
        Bet,
        ExecutionOrder,
        Decision,
        Analysis,
        LLMCall,
        MarketSnapshot,
        PipelineRun,
        WalletSnapshot,
        WalletState,
        Market,
    ):
        result = await db.execute(delete(model))
        deleted[model.__tablename__] = result.rowcount or 0
    await db.commit()
    return {"ok": True, "deleted": deleted}
