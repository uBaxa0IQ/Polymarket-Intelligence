from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class MarketAnalysis(TypedDict, total=False):
    """Per-market state produced by Stage 2 analysis."""
    # From screener
    market_id: str
    condition_id: str | None
    question: str
    market_slug: str | None
    event_title: str | None
    market_description: str
    resolution_date: str
    p_market: float
    category: str

    # From ranker
    research_priority: str | None
    structural_reason: str | None

    # Evidence
    news_evidence: list[dict]
    base_rate_evidence: list[dict]
    evidence_pool: list[str]

    # Debate (variable rounds; full text also in llm_calls)
    debate_messages: list[dict[str, Any]]
    debate_pairs_completed: int | None
    debate_consensus: bool | None
    debate_stop_reason: str | None
    debate_history: list[dict[str, Any]] | None

    # Judge output
    p_yes: float | None
    confidence: float | None
    reasoning: str | None
    gap: float | None

    # Stage 3
    action: str | None
    kelly_fraction: float | None
    bet_size_usd: float | None
    decision_reason: str | None

    # DB IDs
    analysis_db_id: str | None
    decision_db_id: str | None

    # Error
    error: str | None


class PipelineState(TypedDict, total=False):
    """Top-level graph state."""
    # Metadata
    pipeline_run_id: str
    mode: str

    # Config snapshot (frozen at run start)
    config: dict[str, Any]
    prompts: dict[str, str]

    # Stage 1 outputs
    screened_markets: list[dict]
    # Markets selected for analysis (passed to fan-out, NOT the same as analyses)
    markets_to_analyze: list[MarketAnalysis]
    ranked_markets: list[dict]

    # Stage 2: Annotated with operator.add so parallel fan-in APPENDS, not overwrites
    analyses: Annotated[list[MarketAnalysis], operator.add]

    # Errors
    errors: list[str]
