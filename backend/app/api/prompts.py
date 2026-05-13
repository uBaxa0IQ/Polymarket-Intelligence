from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.infra.auth import get_current_user
from app.database import get_db
from app.schemas.settings import PromptOut, PromptUpdate
from app.services.settings_service import settings_service

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[PromptOut])
async def get_all_prompts(db: AsyncSession = Depends(get_db)):
    return await settings_service.get_all_prompts(db)


@router.get("/{name}", response_model=PromptOut)
async def get_prompt(name: str, db: AsyncSession = Depends(get_db)):
    row = await settings_service.get_prompt(db, name)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Prompt '{name}' not found")
    return row


@router.put("/{name}", response_model=PromptOut)
async def update_prompt(name: str, body: PromptUpdate, db: AsyncSession = Depends(get_db)):
    return await settings_service.update_prompt(db, name, body.template, body.description)


@router.post("/reset-defaults", status_code=204)
async def reset_prompt_defaults(db: AsyncSession = Depends(get_db)):
    await settings_service.reset_prompts_defaults(db)
