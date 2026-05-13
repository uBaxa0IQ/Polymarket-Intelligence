"""Stage 1b–1c: ranker, top-N selection, fan-out to per-market analysis."""
from __future__ import annotations

import json
import logging

from langgraph.types import Send

from app.graph import prompts as prompt_helpers
from app.graph.llm_adapter_factory import make_llm_adapter_for_pipeline
from app.graph.llm_retry import call_llm_with_retry
from app.graph.llm_text import parse_json_array
from app.graph.pipeline_persistence import (
    PipelineCancelled,
    log_llm_call,
    market_ids_with_prior_analysis_or_bet,
    raise_if_pipeline_cancelled,
    update_pipeline_run,
)
from app.graph.state import MarketAnalysis, PipelineState

logger = logging.getLogger(__name__)

# Stage 1b: rank_markets
# ---------------------------------------------------------------------------

async def rank_markets(state: PipelineState) -> dict:
    config = state["config"]
    prompts = state["prompts"]
    screened = state.get("screened_markets", [])
    await raise_if_pipeline_cancelled(state["pipeline_run_id"])
    await update_pipeline_run(state["pipeline_run_id"], current_stage="ranker")

    if not screened:
        return {"ranked_markets": []}

    known = await market_ids_with_prior_analysis_or_bet()
    screened_for_rank = [r for r in screened if str(r.get("market_id", "")) not in known]

    if not screened_for_rank:
        await update_pipeline_run(state["pipeline_run_id"], markets_ranked=0)
        return {"ranked_markets": []}

    rk = config.get("ranker", {})
    provider = rk.get("provider", "yandex")
    model = str(rk.get("model", ""))
    temperature = float(rk.get("temperature", 0.15))
    batch_size = int(rk.get("batch_size", 50))
    llm_cfg = config.get("llm", {})
    rpm = int(llm_cfg.get(f"{provider}_requests_per_minute", 20))
    max_retries_429 = int(llm_cfg.get("max_retries_429", 5))
    max_retries_5xx = int(llm_cfg.get("max_retries_5xx", 3))
    agent_timeout = float(config.get("stage2", {}).get("agent_timeout_sec", 150))

    from app.infra.rate_limiter import get_limiter
    limiter = get_limiter(provider, rpm)

    adapter = make_llm_adapter_for_pipeline(provider, config)
    system_msg = prompt_helpers.get_triage_system(prompts)

    # Sort by volume desc so each batch contains comparably liquid markets
    screened_sorted = sorted(
        screened_for_rank,
        key=lambda r: float(r.get("volume", 0)),
        reverse=True,
    )

    # Split into batches (batch_size=0 means no batching)
    if batch_size > 0 and len(screened_sorted) > batch_size:
        batches = [
            screened_sorted[i : i + batch_size]
            for i in range(0, len(screened_sorted), batch_size)
        ]
    else:
        batches = [screened_sorted]

    ranked_all: list[dict] = []

    for batch_idx, batch in enumerate(batches):
        await raise_if_pipeline_cancelled(state["pipeline_run_id"])
        prompt_markets = [
            {
                "market_id": r["market_id"],
                "question": r["question"],
                "event_title": r.get("event_title") or "",
                "tags": r.get("tags_all") or [],
                "p_yes": r.get("yes_implied", 0.5),
                "volume_usd": r.get("volume", 0),
                "days_to_close": round(float(r.get("hours_left", 0)) / 24, 1),
            }
            for r in batch
        ]
        user_msg = json.dumps(prompt_markets, ensure_ascii=False, indent=2)
        max_tokens = min(16384, 800 + 220 * max(1, len(batch)))

        try:
            await limiter.acquire()
            response_raw, duration, meta, input_tokens, output_tokens, retry_count, retry_reason = (
                await call_llm_with_retry(
                    adapter, system_msg, user_msg, model, max_tokens, temperature,
                    False, None, agent_timeout, max_retries_429, max_retries_5xx,
                    None,
                )
            )
            ranked_batch = parse_json_array(response_raw)
            ranked_all.extend(ranked_batch)
            await log_llm_call(
                state["pipeline_run_id"], None, f"ranker_batch_{batch_idx + 1}",
                provider, model, system_msg, user_msg,
                response_raw, ranked_batch, temperature, max_tokens, False, duration, None,
                input_tokens=input_tokens, output_tokens=output_tokens,
                retry_count=retry_count, retry_reason=retry_reason,
            )
        except Exception as exc:
            last_error = str(exc)
            logger.warning(
                "Ranker batch %d/%d failed (%d markets): %s",
                batch_idx + 1, len(batches), len(batch), exc,
            )
            await log_llm_call(
                state["pipeline_run_id"], None, f"ranker_batch_{batch_idx + 1}",
                provider, model, system_msg, user_msg,
                "", None, temperature, max_tokens, False, 0.0, last_error,
            )

    # Fallback: if all batches failed, sort by volume and assign medium priority
    if not ranked_all and screened_for_rank:
        logger.warning("Ranker returned no results — falling back to volume-sorted selection")
        ranked_all = [
            {
                "market_id": r["market_id"],
                "research_priority": "medium",
                "structural_reason": "ranker_fallback_by_volume",
            }
            for r in screened_sorted
        ]

    # Build ranker_results with per-market data
    ranked_by_id = {str(r.get("market_id", "")): r for r in ranked_all}
    screened_lookup = {str(r["market_id"]): r for r in screened_for_rank}
    ranker_markets = []
    for mid, row in screened_lookup.items():
        rank_data = ranked_by_id.get(mid, {})
        ranker_markets.append({
            "id": mid,
            "question": str(row.get("question", "")),
            "research_priority": rank_data.get("research_priority", "unknown"),
            "structural_reason": rank_data.get("structural_reason", ""),
            "ranked": mid in ranked_by_id,
        })

    ranker_results = {
        "total_input": len(screened_for_rank),
        "total_ranked": len(ranked_all),
        "batches": len(batches),
        "markets": ranker_markets,
    }

    await update_pipeline_run(
        state["pipeline_run_id"],
        markets_ranked=len(ranked_all),
        ranker_results=ranker_results,
    )
    return {"ranked_markets": ranked_all}


# ---------------------------------------------------------------------------
# Stage 1c: select_top_n
# ---------------------------------------------------------------------------

async def select_top_n(state: PipelineState) -> dict:
    await raise_if_pipeline_cancelled(state["pipeline_run_id"])
    ranked = state.get("ranked_markets", [])
    screened = state.get("screened_markets", [])
    ranker_cfg = state["config"].get("ranker", {})
    top_n = int(ranker_cfg.get("top_n", 3))
    selection_policy = str(ranker_cfg.get("selection_policy", "top_n")).strip().lower()

    lookup = {str(r["market_id"]): r for r in screened}
    priority_order = {"high": 0, "medium": 1, "low": 2}
    sorted_ranked = sorted(
        ranked,
        key=lambda x: priority_order.get(str(x.get("research_priority", "low")).lower(), 99),
    )
    if selection_policy == "high_only":
        candidates = [r for r in sorted_ranked if str(r.get("research_priority", "")).lower() == "high"]
    elif selection_policy == "high_medium":
        candidates = [r for r in sorted_ranked if str(r.get("research_priority", "")).lower() in {"high", "medium"}]
    else:
        candidates = sorted_ranked

    markets_to_analyze: list[MarketAnalysis] = []
    for r in candidates[:top_n]:
        mid = str(r.get("market_id", ""))
        row = lookup.get(mid, {})
        ma: MarketAnalysis = {
            "market_id": mid,
            "condition_id": row.get("condition_id"),
            "question": str(row.get("question", "")),
            "market_slug": row.get("market_slug"),
            "event_title": row.get("event_title"),
            "market_description": str(row.get("market_description") or row.get("event_title") or ""),
            "resolution_date": str(row.get("endDate") or ""),
            "p_market": float(row.get("yes_implied") or 0.5),
            "category": (row.get("tags_all") or [""])[0],
            "research_priority": r.get("research_priority"),
            "structural_reason": r.get("structural_reason"),
            "news_evidence": [],
            "base_rate_evidence": [],
            "evidence_pool": [],
            "error": None,
        }
        markets_to_analyze.append(ma)

    return {"markets_to_analyze": markets_to_analyze, "analyses": []}


def fan_out_to_markets(state: PipelineState) -> list[Send]:
    return [
        Send("analyze_market", {
            "pipeline_run_id": state["pipeline_run_id"],
            "config": state["config"],
            "prompts": state["prompts"],
            "ma": ma,
        })
        for ma in state.get("markets_to_analyze", [])
    ]

