from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.auth import get_current_user
from app.database import get_db
from app.schemas.settings import SettingOut, SettingUpdate
from app.services.settings_service import settings_service

router = APIRouter(dependencies=[Depends(get_current_user)])

# Must match backend/app/services/betting_service.py
_ALLOWED_TIFS = {"GTC", "IOC", "FAK", "FOK", "GTD"}


def _as_bool(value: object, default: bool) -> bool:
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


@router.get("", response_model=dict[str, list[SettingOut]])
async def get_all_settings(db: AsyncSession = Depends(get_db)):
    rows = await settings_service.get_all(db)
    grouped: dict[str, list] = {}
    for row in rows:
        grouped.setdefault(row.category, []).append(row)
    return grouped


@router.get("/{category}", response_model=list[SettingOut])
async def get_settings_by_category(category: str, db: AsyncSession = Depends(get_db)):
    return await settings_service.get_by_category(db, category)


@router.put("/{category}/{key}", response_model=SettingOut)
async def update_setting(
    category: str,
    key: str,
    body: SettingUpdate,
    db: AsyncSession = Depends(get_db),
):
    if category == "betting" and key == "order_time_in_force":
        tif = str(body.value or "").strip().upper()
        if tif not in _ALLOWED_TIFS:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid order_time_in_force '{body.value}'. Allowed values: {sorted(_ALLOWED_TIFS)}",
            )
        body.value = tif

    if category == "stage2" and key == "mode":
        m = str(body.value or "").strip().lower()
        if m not in {"full", "simple"}:
            raise HTTPException(
                status_code=422,
                detail="stage2.mode must be 'full' or 'simple'",
            )
        body.value = m

    if category == "betting" and key == "dry_run_bankroll_source":
        src = str(body.value or "").strip().lower()
        if src not in {"clob", "settings"}:
            raise HTTPException(
                status_code=422,
                detail="dry_run_bankroll_source must be 'clob' or 'settings'",
            )
        body.value = src

    if category == "copytrading" and key == "target_wallet":
        wallet = str(body.value or "").strip()
        if wallet and (not wallet.startswith("0x") or len(wallet) != 42):
            raise HTTPException(
                status_code=422,
                detail="copytrading.target_wallet must be empty or a valid 0x wallet address",
            )
        body.value = wallet

    if category == "copytrading" and key == "stake_mode":
        mode = str(body.value or "").strip().lower()
        if mode not in {"fixed", "balance_pct", "follow_trader_size"}:
            raise HTTPException(
                status_code=422,
                detail="copytrading.stake_mode must be one of: fixed, balance_pct, follow_trader_size",
            )
        body.value = mode

    if category == "copytrading" and key in {
        "min_bet_usd",
        "stake_balance_pct",
        "stake_trader_ratio",
        "poll_seconds",
        "activity_limit",
        "max_orders_per_hour",
        "slippage",
        "min_balance_buffer_usd",
    }:
        try:
            val = float(body.value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail=f"copytrading.{key} must be numeric")
        if key in {"poll_seconds", "min_bet_usd", "max_orders_per_hour", "min_balance_buffer_usd"} and val <= 0:
            raise HTTPException(status_code=422, detail=f"copytrading.{key} must be > 0")
        if key in {"stake_balance_pct", "stake_trader_ratio"} and val < 0:
            raise HTTPException(status_code=422, detail=f"copytrading.{key} must be >= 0")
        if key == "activity_limit" and (val < 1 or val > 500):
            raise HTTPException(status_code=422, detail="copytrading.activity_limit must be in [1,500]")
        if key == "slippage" and (val < 0 or val > 1):
            raise HTTPException(status_code=422, detail="copytrading.slippage must be in [0,1]")
        body.value = int(val) if key in {"activity_limit", "max_orders_per_hour"} else float(val)

    prev_enabled = None
    if category == "scheduler" and key == "enabled":
        prev_enabled = _as_bool(await settings_service.get_value(db, "scheduler", "enabled"), default=False)

    out = await settings_service.update(db, category, key, body.value, body.description)
    if category == "scheduler":
        from app.services.scheduler_service import scheduler_service

        rows = await settings_service.get_by_category(db, "scheduler")
        cfg: dict[str, Any] = {row.key: row.value for row in rows}
        await scheduler_service.apply_config(
            _as_bool(cfg.get("enabled"), default=False),
            cfg.get("interval_hours"),
            cfg.get("cron_expression"),
            _as_bool(cfg.get("wallet_snapshot_enabled"), default=True),
            cfg.get("wallet_snapshot_interval_minutes"),
            _as_bool(cfg.get("settlement_sync_enabled"), default=True),
            cfg.get("settlement_sync_interval_minutes"),
            _as_bool(cfg.get("order_poll_enabled"), default=True),
            cfg.get("order_poll_interval_seconds"),
            _as_bool(cfg.get("reconcile_stale_drafts_enabled"), default=True),
            cfg.get("reconcile_interval_seconds"),
            cfg.get("reconcile_older_than_sec"),
        )

        # Optional one-shot launch when auto-run is enabled.
        now_enabled = _as_bool(cfg.get("enabled"), default=False)
        run_now_on_enable = _as_bool(cfg.get("run_immediately_on_enable"), default=False)
        if key == "enabled" and prev_enabled is False and now_enabled and run_now_on_enable:
            from app.services.pipeline_service import pipeline_service

            run_id = await pipeline_service.start_run(db, trigger="auto_enable")
            if run_id is not None:
                asyncio.create_task(pipeline_service.execute_full_pipeline(run_id))
    return out


@router.post("/reset-defaults", status_code=204)
async def reset_defaults(db: AsyncSession = Depends(get_db)):
    await settings_service.reset_defaults(db)
    from app.services.scheduler_service import scheduler_service

    rows = await settings_service.get_by_category(db, "scheduler")
    cfg = {row.key: row.value for row in rows}
    await scheduler_service.apply_config(
        _as_bool(cfg.get("enabled"), default=False),
        cfg.get("interval_hours"),
        cfg.get("cron_expression"),
        _as_bool(cfg.get("wallet_snapshot_enabled"), default=True),
        cfg.get("wallet_snapshot_interval_minutes"),
        _as_bool(cfg.get("settlement_sync_enabled"), default=True),
        cfg.get("settlement_sync_interval_minutes"),
        _as_bool(cfg.get("order_poll_enabled"), default=True),
        cfg.get("order_poll_interval_seconds"),
        _as_bool(cfg.get("reconcile_stale_drafts_enabled"), default=True),
        cfg.get("reconcile_interval_seconds"),
        cfg.get("reconcile_older_than_sec"),
    )
