"""DB writes for pipeline runs, LLM calls, and market rows used from LangGraph nodes."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import async_session_factory
from app.graph.llm_cost import calc_llm_cost_usd
from app.graph.llm_text import parse_iso_datetime
from app.models.llm_call import LLMCall
from app.models.market import Market
from app.models.pipeline_run import PipelineRun


class PipelineCancelled(Exception):
    """Raised when the run row is ``cancelled`` (user requested stop)."""


async def raise_if_pipeline_cancelled(pipeline_run_id: str) -> None:
    async with async_session_factory() as db:
        r = await db.get(PipelineRun, uuid.UUID(pipeline_run_id))
        if r is not None and r.status == "cancelled":
            raise PipelineCancelled()


async def log_llm_call(
    pipeline_run_id: str,
    market_id: str | None,
    stage: str,
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    response_raw: str,
    response_parsed: Any,
    temperature: float,
    max_tokens: int,
    web_search: bool,
    duration: float,
    error: str | None = None,
    call_metadata: dict | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    retry_count: int = 0,
    retry_reason: str | None = None,
) -> None:
    cost_usd = None
    if input_tokens is not None and output_tokens is not None:
        cost_usd = calc_llm_cost_usd(model, input_tokens, output_tokens)

    async with async_session_factory() as db:
        call = LLMCall(
            id=uuid.uuid4(),
            pipeline_run_id=uuid.UUID(pipeline_run_id),
            market_id=market_id,
            stage=stage,
            provider=provider,
            model=model,
            system_prompt=system_prompt[:10000] if system_prompt else None,
            user_prompt=user_prompt[:100000] if user_prompt else None,
            response_raw=response_raw[:100000] if response_raw else None,
            response_parsed=response_parsed if isinstance(response_parsed, (dict, list)) else None,
            temperature=temperature,
            max_tokens=max_tokens,
            web_search_enabled=web_search,
            call_metadata=call_metadata,
            duration_seconds=duration,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            retry_count=retry_count,
            retry_reason=retry_reason,
            error=error,
        )
        db.add(call)
        await db.commit()


async def upsert_market_row(row: dict) -> None:
    market_id = str(row.get("market_id", ""))
    if not market_id:
        return
    async with async_session_factory() as db:
        end_date_raw = row.get("endDate") or row.get("resolution_date")
        end_date = parse_iso_datetime(end_date_raw)
        tags_val = row.get("tags_all") or ([row["category"]] if row.get("category") else [])
        stmt = (
            pg_insert(Market)
            .values(
                id=uuid.uuid4(),
                market_id=market_id,
                condition_id=row.get("condition_id"),
                question=str(row.get("question", "")),
                market_slug=row.get("market_slug"),
                event_id=row.get("event_id"),
                event_title=row.get("event_title"),
                tags=tags_val,
                end_date=end_date,
            )
            .on_conflict_do_update(
                index_elements=["market_id"],
                set_={
                    "last_seen_at": datetime.now(timezone.utc),
                    "question": str(row.get("question", "")),
                    "market_slug": row.get("market_slug"),
                    "event_title": row.get("event_title"),
                    "end_date": end_date,
                },
            )
        )
        await db.execute(stmt)
        await db.commit()


async def update_pipeline_run(pipeline_run_id: str, **fields: Any) -> None:
    async with async_session_factory() as db:
        r = await db.get(PipelineRun, uuid.UUID(pipeline_run_id))
        if r:
            for k, v in fields.items():
                setattr(r, k, v)
            await db.commit()


async def market_ids_with_prior_analysis_or_bet() -> set[str]:
    async with async_session_factory() as db:
        res = await db.execute(
            text(
                "SELECT DISTINCT market_id FROM analyses "
                "UNION "
                "SELECT DISTINCT market_id FROM bets"
            )
        )
        return {str(row[0]) for row in res.all() if row[0] is not None}
