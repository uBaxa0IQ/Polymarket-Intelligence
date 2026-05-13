from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.auth import get_current_user
from app.database import get_db
from app.models.analysis import Analysis
from app.models.bet import Bet
from app.models.market import Market
from app.models.pipeline_run import PipelineRun

router = APIRouter(dependencies=[Depends(get_current_user)])


def _polymarket_market_url(market_slug: str | None) -> str | None:
    if not market_slug or not str(market_slug).strip():
        return None
    s = str(market_slug).strip()
    return f"https://polymarket.com/market/{quote(s, safe='/-_.~')}"


def _period_start(period: str) -> datetime | None:
    now = datetime.now(timezone.utc)
    if period == "7d":
        return now - timedelta(days=7)
    if period == "30d":
        return now - timedelta(days=30)
    return None


def _non_dry_run_filter():
    return Bet.status != "dry_run"


@router.get("/summary")
async def get_summary(
    db: AsyncSession = Depends(get_db),
    include_wallet: bool = Query(False, description="If true, attach CLOB + Data API wallet snapshot"),
):
    total_runs = (await db.execute(select(func.count()).select_from(PipelineRun))).scalar() or 0

    total_bets = (await db.execute(select(func.count()).select_from(Bet))).scalar() or 0
    dry_run_bets = (
        await db.execute(select(func.count()).select_from(Bet).where(Bet.status == "dry_run"))
    ).scalar() or 0
    executed_bets = total_bets - dry_run_bets

    # P&L and win rate: real money only (exclude dry_run)
    pnl_result = await db.execute(
        select(func.sum(Bet.pnl)).where(Bet.resolved == True, _non_dry_run_filter())
    )
    total_pnl = pnl_result.scalar() or 0.0

    won = (
        await db.execute(
            select(func.count()).select_from(Bet).where(
                Bet.resolved == True, Bet.pnl > 0, _non_dry_run_filter()
            )
        )
    ).scalar() or 0
    resolved = (
        await db.execute(
            select(func.count()).select_from(Bet).where(Bet.resolved == True, _non_dry_run_filter())
        )
    ).scalar() or 0
    win_rate = (won / resolved) if resolved > 0 else None

    total_analyses = (await db.execute(select(func.count()).select_from(Analysis))).scalar() or 0
    gap_result = await db.execute(select(func.avg(func.abs(Analysis.gap))))
    avg_gap = gap_result.scalar()

    lr = await db.execute(
        select(PipelineRun.started_at, PipelineRun.status)
        .order_by(PipelineRun.started_at.desc())
        .limit(1)
    )
    last_row = lr.first()
    last_run_at = last_row[0].isoformat() if last_row and last_row[0] else None
    last_run_status = last_row[1] if last_row else None

    from app.services.settings_service import settings_service

    cfg = await settings_service.get_all_as_dict(db)
    bankroll = (cfg.get("stage3") or {}).get("bankroll_usd")

    out: dict = {
        "total_runs": total_runs,
        "total_bets": total_bets,
        "dry_run_bets": dry_run_bets,
        "executed_bets": executed_bets,
        "total_pnl": round(float(total_pnl), 2) if total_pnl else 0.0,
        "win_rate": round(win_rate, 4) if win_rate is not None else None,
        "total_analyses": total_analyses,
        "avg_gap": round(float(avg_gap), 3) if avg_gap else None,
        "bankroll_usd": bankroll,
        "last_run_at": last_run_at,
        "last_run_status": last_run_status,
    }
    if include_wallet:
        from app.services.wallet_service import wallet_service

        out["wallet"] = await wallet_service.get_snapshot(cfg)
    return out


@router.get("/pnl-chart")
async def get_pnl_chart(
    db: AsyncSession = Depends(get_db),
    period: str = Query("all", pattern="^(7d|30d|all)$"),
    exclude_dry_run: bool = Query(True, description="If true, omit dry_run bets from the series"),
):
    since = _period_start(period)
    q = (
        select(func.coalesce(Bet.resolved_at, Bet.filled_at), Bet.pnl)
        .where(Bet.resolved == True, Bet.pnl.is_not(None))
        .order_by(func.coalesce(Bet.resolved_at, Bet.filled_at))
    )
    if exclude_dry_run:
        q = q.where(_non_dry_run_filter())
    if since is not None:
        q = q.where(func.coalesce(Bet.resolved_at, Bet.filled_at) >= since)
    result = await db.execute(q)
    rows = result.all()
    cumulative = 0.0
    points = []
    for filled_at, pnl in rows:
        cumulative += pnl or 0
        points.append({
            "date": filled_at.isoformat() if filled_at else None,
            "pnl": round(pnl or 0, 2),
            "cumulative": round(cumulative, 2),
            "cumulative_pnl": round(cumulative, 2),
        })
    return points


@router.get("/accuracy")
async def get_accuracy(db: AsyncSession = Depends(get_db)):
    """Calibration: predicted p_yes vs gap buckets."""
    result = await db.execute(
        select(Analysis.p_yes, Analysis.gap).where(Analysis.p_yes.is_not(None))
    )
    rows = result.all()
    buckets: dict[str, list] = {}
    for p_yes, gap in rows:
        bucket = f"{int(p_yes * 10) * 10}-{int(p_yes * 10) * 10 + 10}%"
        buckets.setdefault(bucket, []).append(float(gap or 0))

    return [
        {"bucket": k, "count": len(v), "avg_gap": round(sum(v) / len(v), 3)}
        for k, v in sorted(buckets.items())
    ]


@router.get("/recent-activity")
async def get_recent_activity(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    rq = select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(5)
    runs = await db.execute(rq)
    bq = (
        select(Bet, Market.question, Market.market_slug)
        .outerjoin(Market, Market.market_id == Bet.market_id)
        .order_by(Bet.placed_at.desc())
        .limit(10)
    )
    bets = await db.execute(bq)
    events = []
    for r in runs.scalars():
        events.append({
            "type": "run",
            "id": str(r.id),
            "status": r.status,
            "trigger": r.trigger,
            "at": r.started_at.isoformat() if r.started_at else None,
        })
    for b, question, market_slug in bets.all():
        slug = market_slug if market_slug and str(market_slug).strip() else None
        events.append({
            "type": "bet",
            "id": str(b.id),
            "market_id": b.market_id,
            "question": question,
            "market_slug": slug,
            "polymarket_url": _polymarket_market_url(slug),
            "side": b.side,
            "amount_usd": b.amount_usd,
            "status": b.status,
            "pnl": b.pnl,
            "at": b.placed_at.isoformat() if b.placed_at else None,
        })
    events.sort(key=lambda e: e["at"] or "", reverse=True)
    return events[:limit]
