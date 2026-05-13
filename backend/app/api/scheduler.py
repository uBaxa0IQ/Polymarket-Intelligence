from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.auth import get_current_user
from app.database import get_db

router = APIRouter(dependencies=[Depends(get_current_user)])


class ScheduleConfig(BaseModel):
    enabled: bool
    run_immediately_on_enable: bool | None = None
    interval_hours: float | None = None
    cron_expression: str | None = None
    wallet_snapshot_enabled: bool | None = None
    wallet_snapshot_interval_minutes: float | None = None
    settlement_sync_enabled: bool | None = None
    settlement_sync_interval_minutes: float | None = None
    order_poll_enabled: bool | None = None
    order_poll_interval_seconds: float | None = None
    reconcile_stale_drafts_enabled: bool | None = None
    reconcile_interval_seconds: float | None = None
    reconcile_older_than_sec: float | None = None


@router.get("")
async def get_schedule(db: AsyncSession = Depends(get_db)):
    from app.services.scheduler_service import scheduler_service
    from app.services.settings_service import settings_service

    rows = await settings_service.get_by_category(db, "scheduler")
    cfg = {row.key: row.value for row in rows}
    status = await scheduler_service.get_status()
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "run_immediately_on_enable": bool(cfg.get("run_immediately_on_enable", False)),
        "interval_hours": float(cfg.get("interval_hours") or 6),
        "cron_expression": cfg.get("cron_expression") or None,
        "wallet_snapshot_enabled": bool(cfg.get("wallet_snapshot_enabled", True)),
        "wallet_snapshot_interval_minutes": float(cfg.get("wallet_snapshot_interval_minutes") or 5),
        "settlement_sync_enabled": bool(cfg.get("settlement_sync_enabled", True)),
        "settlement_sync_interval_minutes": float(cfg.get("settlement_sync_interval_minutes") or 30),
        "order_poll_enabled": bool(cfg.get("order_poll_enabled", True)),
        "order_poll_interval_seconds": float(cfg.get("order_poll_interval_seconds") or 15),
        "reconcile_stale_drafts_enabled": bool(cfg.get("reconcile_stale_drafts_enabled", True)),
        "reconcile_interval_seconds": float(cfg.get("reconcile_interval_seconds") or 60),
        "reconcile_older_than_sec": float(cfg.get("reconcile_older_than_sec") or 60),
        **status,
    }


@router.put("")
async def update_schedule(body: ScheduleConfig, db: AsyncSession = Depends(get_db)):
    import asyncio
    from app.services.scheduler_service import scheduler_service
    from app.services.settings_service import settings_service

    prev_enabled_rows = await settings_service.get_by_category(db, "scheduler")
    prev_cfg = {row.key: row.value for row in prev_enabled_rows}
    prev_enabled = bool(prev_cfg.get("enabled", False))

    await settings_service.update(db, "scheduler", "enabled", body.enabled)
    if body.run_immediately_on_enable is not None:
        await settings_service.update(
            db,
            "scheduler",
            "run_immediately_on_enable",
            body.run_immediately_on_enable,
        )
    await settings_service.update(db, "scheduler", "interval_hours", body.interval_hours)
    await settings_service.update(db, "scheduler", "cron_expression", body.cron_expression)
    if body.wallet_snapshot_enabled is not None:
        await settings_service.update(db, "scheduler", "wallet_snapshot_enabled", body.wallet_snapshot_enabled)
    if body.wallet_snapshot_interval_minutes is not None:
        await settings_service.update(
            db,
            "scheduler",
            "wallet_snapshot_interval_minutes",
            body.wallet_snapshot_interval_minutes,
        )
    if body.settlement_sync_enabled is not None:
        await settings_service.update(db, "scheduler", "settlement_sync_enabled", body.settlement_sync_enabled)
    if body.settlement_sync_interval_minutes is not None:
        await settings_service.update(
            db,
            "scheduler",
            "settlement_sync_interval_minutes",
            body.settlement_sync_interval_minutes,
        )
    if body.order_poll_enabled is not None:
        await settings_service.update(db, "scheduler", "order_poll_enabled", body.order_poll_enabled)
    if body.order_poll_interval_seconds is not None:
        await settings_service.update(
            db, "scheduler", "order_poll_interval_seconds", body.order_poll_interval_seconds
        )
    if body.reconcile_stale_drafts_enabled is not None:
        await settings_service.update(
            db, "scheduler", "reconcile_stale_drafts_enabled", body.reconcile_stale_drafts_enabled
        )
    if body.reconcile_interval_seconds is not None:
        await settings_service.update(db, "scheduler", "reconcile_interval_seconds", body.reconcile_interval_seconds)
    if body.reconcile_older_than_sec is not None:
        await settings_service.update(
            db, "scheduler", "reconcile_older_than_sec", body.reconcile_older_than_sec
        )

    rows = await settings_service.get_by_category(db, "scheduler")
    up_cfg = {row.key: row.value for row in rows}
    await scheduler_service.apply_config(
        body.enabled,
        up_cfg.get("interval_hours"),
        up_cfg.get("cron_expression"),
        bool(up_cfg.get("wallet_snapshot_enabled", True)),
        float(up_cfg.get("wallet_snapshot_interval_minutes") or 5.0),
        bool(up_cfg.get("settlement_sync_enabled", True)),
        float(up_cfg.get("settlement_sync_interval_minutes") or 30.0),
        bool(up_cfg.get("order_poll_enabled", True)),
        float(up_cfg.get("order_poll_interval_seconds") or 15.0),
        bool(up_cfg.get("reconcile_stale_drafts_enabled", True)),
        float(up_cfg.get("reconcile_interval_seconds") or 60.0),
        up_cfg.get("reconcile_older_than_sec") or 60.0,
    )

    run_now_on_enable = (
        body.run_immediately_on_enable
        if body.run_immediately_on_enable is not None
        else bool(prev_cfg.get("run_immediately_on_enable", False))
    )
    if (not prev_enabled) and body.enabled and run_now_on_enable:
        from app.services.pipeline_service import pipeline_service

        run_id = await pipeline_service.start_run(db, trigger="auto_enable")
        if run_id is not None:
            asyncio.create_task(pipeline_service.execute_full_pipeline(run_id))

    return {"status": "updated"}


@router.post("/run-now", response_model=dict)
async def run_now(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    from app.services.pipeline_service import pipeline_service

    run_id = await pipeline_service.start_run(db, trigger="scheduled")
    if run_id is None:
        from fastapi import HTTPException

        raise HTTPException(409, "A pipeline run is already in progress")
    background_tasks.add_task(pipeline_service.execute_full_pipeline, run_id=run_id)
    return {"run_id": str(run_id)}
