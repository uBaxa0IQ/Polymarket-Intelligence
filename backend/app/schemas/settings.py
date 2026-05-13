from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SettingOut(BaseModel):
    id: int
    category: str
    key: str
    value: Any
    description: str | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class SettingUpdate(BaseModel):
    value: Any
    description: str | None = None


class PromptOut(BaseModel):
    id: int
    name: str
    template: str
    description: str | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class PromptUpdate(BaseModel):
    template: str
    description: str | None = None
