from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import and_, select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.auth import get_current_user
from app.database import get_db
from app.models.analysis import Analysis
from app.models.decision import Decision
from app.models.market import Market
from app.models.pipeline_run import PipelineRun
from app.schemas.pipeline import (
    PipelineRunAccepted,
    PipelineRunOut,
    PipelineRunTriggerBody,
)

router = APIRouter()


@router.post("/run", response_model=PipelineRunAccepted, dependencies=[Depends(get_current_user)])
async def trigger_run(
    body: PipelineRunTriggerBody,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    from app.services.pipeline_service import pipeline_service
    run_id = await pipeline_service.start_run(db, trigger="manual", top_n=body.top_n)
    if run_id is None:
        raise HTTPException(409, "A pipeline run is already in progress")
    background_tasks.add_task(pipeline_service.execute_full_pipeline, run_id=run_id)
    return PipelineRunAccepted(run_id=str(run_id))


@router.get("/runs", response_model=list[PipelineRunOut], dependencies=[Depends(get_current_user)])
async def list_runs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    q = select(PipelineRun).order_by(desc(PipelineRun.started_at))
    result = await db.execute(q.offset(offset).limit(limit))
    return list(result.scalars().all())


@router.get("/runs/active", dependencies=[Depends(get_current_user)])
async def get_active_run(db: AsyncSession = Depends(get_db)):
    """Return the currently running/pending run, if any."""
    result = await db.execute(
        select(PipelineRun)
        .where(PipelineRun.status.in_(["pending", "running"]))
        .order_by(desc(PipelineRun.started_at))
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if run is None:
        return None
    target = run.markets_ranked if (run.markets_ranked and run.markets_ranked > 0) else None
    progress = None if target is None else min(1.0, max(0.0, run.markets_analyzed / target))
    return {
        "id": str(run.id),
        "status": run.status,
        "current_stage": run.current_stage,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "markets_screened": run.markets_screened,
        "markets_ranked": run.markets_ranked,
        "markets_analyzed": run.markets_analyzed,
        "analysis_target": target,
        "progress": progress,
    }


@router.get("/runs/{run_id}", response_model=PipelineRunOut, dependencies=[Depends(get_current_user)])
async def get_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Run not found")
    return row


@router.get("/runs/{run_id}/screener", dependencies=[Depends(get_current_user)])
async def get_run_screener(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "Run not found")
    return run.screener_results or {}


@router.get("/runs/{run_id}/ranker", dependencies=[Depends(get_current_user)])
async def get_run_ranker(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(404, "Run not found")
    return run.ranker_results or {}


_EXEC_EVENT_SEVERITIES = frozenset({"debug", "info", "warn", "error", "critical"})


@router.get("/runs/{run_id}/trace", dependencies=[Depends(get_current_user)])
async def get_run_decision_and_execution_trace(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    events_limit: int = Query(200, ge=1, le=5000, description="Page size for execution_events"),
    events_offset: int = Query(0, ge=0, description="Offset into execution_events (same filters)"),
    severity: str | None = Query(
        None,
        description="Filter events by severity: debug, info, warn, error, critical",
    ),
    stage: str | None = Query(None, description="Filter events by stage (exact match)"),
):
    """Decision math trace (sizing, EV) + append-only execution events for this run.

    Decisions are only included when ``events_offset == 0`` to avoid duplicating a large
    payload on every infinite-scroll page. Execution events are paginated; use
    ``execution_events_total`` for UI.
    """
    from app.models.bet_execution_event import BetExecutionEvent

    result = await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(404, "Run not found")

    if severity is not None and severity != "":
        s = severity.strip().lower()
        if s not in _EXEC_EVENT_SEVERITIES:
            raise HTTPException(
                422,
                f"Invalid severity. Allowed: {sorted(_EXEC_EVENT_SEVERITIES)}",
            )
    else:
        s = None

    stage_f = (stage or "").strip() or None

    dec_out: list[dict] = []
    if events_offset == 0:
        drows = await db.execute(
            select(Decision)
            .where(Decision.pipeline_run_id == run_id)
            .order_by(Decision.created_at)
        )
        decisions = drows.scalars().all()
        dec_out = [
            {
                "id": str(d.id),
                "market_id": d.market_id,
                "action": d.action,
                "reason": d.reason,
                "bet_size_usd": d.bet_size_usd,
                "kelly_fraction": d.kelly_fraction,
                "p_yes": d.p_yes,
                "p_market": d.p_market,
                "gap": d.gap,
                "decision_trace": d.decision_trace,
            }
            for d in decisions
        ]

    ev_conds: list = [BetExecutionEvent.pipeline_run_id == run_id]
    if s is not None:
        ev_conds.append(BetExecutionEvent.severity == s)
    if stage_f is not None:
        ev_conds.append(BetExecutionEvent.stage == stage_f)

    ev_base = and_(*ev_conds)
    count_stmt = select(func.count()).select_from(BetExecutionEvent).where(ev_base)
    total = int((await db.execute(count_stmt)).scalar_one() or 0)

    ev_result = await db.execute(
        select(BetExecutionEvent)
        .where(ev_base)
        .order_by(BetExecutionEvent.event_time, BetExecutionEvent.id)
        .offset(events_offset)
        .limit(events_limit)
    )
    events = ev_result.scalars().all()
    ev_out = [
        {
            "id": e.id,
            "decision_id": str(e.decision_id) if e.decision_id else None,
            "bet_id": str(e.bet_id) if e.bet_id else None,
            "event_time": e.event_time.isoformat() if e.event_time else None,
            "stage": e.stage,
            "event_type": e.event_type,
            "severity": e.severity,
            "client_order_id": e.client_order_id,
            "exchange_order_id": e.exchange_order_id,
            "payload": e.payload,
        }
        for e in events
    ]
    return {
        "decisions": dec_out,
        "execution_events": ev_out,
        "execution_events_total": total,
        "execution_events_limit": events_limit,
        "execution_events_offset": events_offset,
    }


@router.get("/runs/{run_id}/analyses", dependencies=[Depends(get_current_user)])
async def get_run_analyses_summary(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(404, "Run not found")

    stmt = (
        select(Analysis, Decision.action, Decision.bet_size_usd, Decision.kelly_fraction,
               Decision.reason, Market.question)
        .outerjoin(Decision, Decision.analysis_id == Analysis.id)
        .join(Market, Market.market_id == Analysis.market_id)
        .where(Analysis.pipeline_run_id == run_id)
        .order_by(Analysis.created_at)
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "market_id": a.market_id,
            "question": q,
            "p_yes": a.p_yes,
            "p_market": a.p_market,
            "gap": a.gap,
            "confidence": a.confidence,
            "action": str(act) if act is not None else None,
            "skip_reason": reason,
            "bet_size_usd": bsz,
            "kelly_fraction": kf,
            "debate_pairs_completed": a.debate_pairs_completed,
            "debate_consensus": a.debate_consensus,
            "debate_stop_reason": a.debate_stop_reason,
            "failed_stages": a.failed_stages,
            "research_priority": a.research_priority,
        }
        for a, act, bsz, kf, reason, q in rows
    ]


@router.get("/runs/{run_id}/llm-calls", dependencies=[Depends(get_current_user)])
async def get_run_llm_calls(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    from app.models.llm_call import LLMCall
    result = await db.execute(
        select(LLMCall).where(LLMCall.pipeline_run_id == run_id).order_by(LLMCall.created_at)
    )
    calls = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "stage": c.stage,
            "market_id": c.market_id,
            "provider": c.provider,
            "model": c.model,
            "duration_seconds": c.duration_seconds,
            "input_tokens": c.input_tokens,
            "output_tokens": c.output_tokens,
            "cost_usd": c.cost_usd,
            "retry_count": c.retry_count,
            "retry_reason": c.retry_reason,
            "web_search_enabled": c.web_search_enabled,
            "error": c.error,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "response_raw": c.response_raw,
            "response_parsed": c.response_parsed,
        }
        for c in calls
    ]


@router.get("/runs/{run_id}/markets/{market_id}", dependencies=[Depends(get_current_user)])
async def get_run_market_detail(run_id: uuid.UUID, market_id: str, db: AsyncSession = Depends(get_db)):
    from app.models.llm_call import LLMCall
    result = await db.execute(
        select(Analysis).where(Analysis.pipeline_run_id == run_id, Analysis.market_id == market_id)
    )
    analysis = result.scalar_one_or_none()
    if analysis is None:
        raise HTTPException(404, "Analysis not found")

    calls_result = await db.execute(
        select(LLMCall).where(
            LLMCall.pipeline_run_id == run_id, LLMCall.market_id == market_id
        ).order_by(LLMCall.created_at)
    )
    calls = calls_result.scalars().all()

    return {
        "analysis": {
            "id": str(analysis.id),
            "market_id": analysis.market_id,
            "research_priority": analysis.research_priority,
            "structural_reason": analysis.structural_reason,
            "evidence_pool": analysis.evidence_pool,
            "p_yes": analysis.p_yes,
            "confidence": analysis.confidence,
            "reasoning": analysis.reasoning,
            "p_market": analysis.p_market,
            "gap": analysis.gap,
            "debate_pairs_completed": analysis.debate_pairs_completed,
            "debate_consensus": analysis.debate_consensus,
            "debate_stop_reason": analysis.debate_stop_reason,
            "debate_history": analysis.debate_history,
            "failed_stages": analysis.failed_stages,
        },
        "llm_calls": [
            {
                "id": str(c.id),
                "stage": c.stage,
                "system_prompt": c.system_prompt,
                "user_prompt": c.user_prompt,
                "response_raw": c.response_raw,
                "response_parsed": c.response_parsed,
                "duration_seconds": c.duration_seconds,
                "input_tokens": c.input_tokens,
                "output_tokens": c.output_tokens,
                "cost_usd": c.cost_usd,
                "retry_count": c.retry_count,
                "retry_reason": c.retry_reason,
                "web_search_enabled": c.web_search_enabled,
                "error": c.error,
            }
            for c in calls
        ],
    }


@router.post("/runs/{run_id}/cancel", status_code=204, dependencies=[Depends(get_current_user)])
async def cancel_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PipelineRun).where(PipelineRun.id == run_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Run not found")
    if row.status not in ("pending", "running"):
        raise HTTPException(400, f"Cannot cancel run in status {row.status}")
    row.status = "cancelled"
    row.current_stage = "cancelled"
    await db.commit()
