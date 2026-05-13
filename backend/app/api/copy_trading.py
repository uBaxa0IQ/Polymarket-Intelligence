from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.infra.auth import get_current_user
from app.services.copy_trading_service import copy_trading_service
from app.services.settings_service import settings_service

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/status")
async def get_copy_trading_status():
    return await copy_trading_service.get_status()


@router.post("/start")
async def start_copy_trading(db: AsyncSession = Depends(get_db)):
    await settings_service.update(
        db,
        "copytrading",
        "enabled",
        True,
        "Enable copy-trading worker loop",
    )
    return await copy_trading_service.get_status()


@router.post("/stop")
async def stop_copy_trading(db: AsyncSession = Depends(get_db)):
    await settings_service.update(
        db,
        "copytrading",
        "enabled",
        False,
        "Enable copy-trading worker loop",
    )
    return await copy_trading_service.get_status()
