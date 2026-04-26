"""HTTP response models for pipeline runs (OpenAPI contract)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PipelineRunOut(BaseModel):
    """Single pipeline run row returned by list/get run endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    started_at: datetime | None = None
    finished_at: datetime | None = None
    status: str
    trigger: str
    current_stage: str | None = None
    config_snapshot: dict | None = None
    markets_screened: int = 0
    markets_ranked: int = 0
    markets_analyzed: int = 0
    decisions_count: int = 0
    bets_placed: int = 0
    error_message: str | None = None


class PipelineRunTriggerBody(BaseModel):
    """POST /pipeline/run body."""

    top_n: int | None = Field(default=None, description="Optional override for ranker top_n")


class PipelineRunAccepted(BaseModel):
    """POST /pipeline/run response."""

    run_id: str
