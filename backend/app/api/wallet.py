from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.auth import get_current_user
from app.database import get_db
from app.services.settings_service import settings_service
from app.services.wallet_service import wallet_service

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/summary")
async def wallet_summary(db: AsyncSession = Depends(get_db)):
    """Signer address, CLOB USDC collateral, Data API open-position value."""
    cfg = await settings_service.get_all_as_dict(db)
    return await wallet_service.get_snapshot(cfg)


@router.post("/snapshot")
async def take_snapshot(db: AsyncSession = Depends(get_db)):
    """Manually trigger a wallet snapshot and save it to history."""
    cfg = await settings_service.get_all_as_dict(db)
    await wallet_service.save_snapshot(cfg)
    return {"ok": True}


@router.get("/history")
async def wallet_history(limit: int = Query(200, ge=1, le=1000)):
    """Return recent wallet balance snapshots (newest first)."""
    return await wallet_service.get_history(limit=limit)
