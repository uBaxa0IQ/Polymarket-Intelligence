"""Stage 2: per-market LLM analysis (simple and full pipeline)."""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.graph import prompts as prompt_helpers
from app.graph.llm_adapter_factory import make_llm_adapter_for_pipeline
from app.graph.llm_retry import call_llm_with_retry
from app.graph.llm_text import (
    format_base_rate_lines,
    format_news_lines,
    normalize_debate_control,
    parse_debate_control_footer,
    parse_json_array,
    parse_json_object,
    stage2_web_search_query,
    strip_debate_footer,
)
from app.graph.pipeline_persistence import (
    PipelineCancelled,
    log_llm_call,
    raise_if_pipeline_cancelled,
    update_pipeline_run,
    upsert_market_row,
)
from app.graph.state import MarketAnalysis

logger = logging.getLogger(__name__)

async def analyze_market(state: dict) -> dict:
    """Full Stage 2 pipeline for a single market."""
    pipeline_run_id: str = state["pipeline_run_id"]
    config: dict = state["config"]
    prompts: dict = state["prompts"]
    ma: MarketAnalysis = state["ma"]
    market_id = ma["market_id"]
    await raise_if_pipeline_cancelled(pipeline_run_id)
    await update_pipeline_run(pipeline_run_id, current_stage="analysis")

    await upsert_market_row(ma)

    s2 = config.get("stage2", {})
    provider = str(s2.get("provider", "yandex"))
    model = str(s2.get("model", ""))
    temperature = float(s2.get("temperature", 0.2))
    t_evidence = float(s2.get("temperature_evidence", temperature))
    t_debate = float(s2.get("temperature_debate", temperature))
    t_judge_temp = float(s2.get("temperature_judge", temperature))
    web = bool(s2.get("enable_web_search", True))
    ws_mode_raw = str(s2.get("web_search_mode", "")).strip().lower()
    ws_mode_arg = ws_mode_raw if ws_mode_raw else None
    mt_news = int(s2.get("max_tokens_news", 6000))
    mt_base = int(s2.get("max_tokens_base_rate", 6000))
    mt_debate = int(s2.get("max_tokens_debate", 4500))
    mt_judge = int(s2.get("max_tokens_judge", 4000))
    max_pairs = max(1, int(s2.get("max_debate_rounds", 3)))
    convergence_threshold = float(s2.get("debate_convergence_threshold", 0.08))
    agent_timeout = float(s2.get("agent_timeout_sec", 150))
    market_timeout = float(s2.get("market_timeout_sec", 600))

    llm_cfg = config.get("llm", {})
    rpm = int(llm_cfg.get(f"{provider}_requests_per_minute", 20))
    max_retries_429 = int(llm_cfg.get("max_retries_429", 5))
    max_retries_5xx = int(llm_cfg.get("max_retries_5xx", 3))

    from app.infra.rate_limiter import get_limiter
    limiter = get_limiter(provider, rpm)

    adapter = make_llm_adapter_for_pipeline(provider, config)

    async def _call(
        system: str,
        user: str,
        max_tokens: int,
        web_search: bool,
        temp: float | None = None,
        *,
        web_search_query: str | None = None,
    ) -> tuple[str, float, dict, int | None, int | None, int, str | None]:
        await limiter.acquire()
        return await call_llm_with_retry(
            adapter, system, user, model, max_tokens, temp if temp is not None else temperature,
            web_search, ws_mode_arg, agent_timeout, max_retries_429, max_retries_5xx,
            web_search_query,
        )

    mode = str(s2.get("mode", "full")).strip().lower()
    mt_simple = int(s2.get("max_tokens_simple", 8000))

    try:
        if mode == "simple":
            coro = _analyze_market_simple(
                pipeline_run_id, prompts, ma, market_id,
                provider, model, _call,
                max_tokens=mt_simple, temperature=t_judge_temp,
            )
        else:
            coro = _analyze_market_inner(
                pipeline_run_id, config, prompts, ma, market_id,
                provider, model, temperature, web, mt_news, mt_base, mt_debate, mt_judge,
                max_pairs, convergence_threshold, _call,
                t_evidence=t_evidence, t_debate=t_debate, t_judge=t_judge_temp,
            )
        result = await asyncio.wait_for(coro, timeout=market_timeout)
        return result
    except PipelineCancelled:
        raise
    except asyncio.TimeoutError:
        logger.error("Market analysis timeout for %s after %.0fs", market_id, market_timeout)
        failed_stages = [{"stage": "all", "reason": f"market_timeout_{market_timeout}s"}]
        await _save_failed_analysis(pipeline_run_id, ma, failed_stages)
        return {"analyses": [{**ma, "p_yes": None, "confidence": None, "gap": None,
                               "failed_stages": failed_stages, "analysis_db_id": None}]}
    except Exception as exc:
        logger.error("Market analysis error for %s: %s", market_id, exc)
        failed_stages = [{"stage": "all", "reason": str(exc)[:200]}]
        await _save_failed_analysis(pipeline_run_id, ma, failed_stages)
        return {"analyses": [{**ma, "p_yes": None, "confidence": None, "gap": None,
                               "failed_stages": failed_stages, "analysis_db_id": None}]}


async def _save_failed_analysis(pipeline_run_id: str, ma: dict, failed_stages: list) -> None:
    from app.models.analysis import Analysis
    from app.database import async_session_factory
    analysis_id = uuid.uuid4()
    async with async_session_factory() as db:
        db.add(Analysis(
            id=analysis_id,
            pipeline_run_id=uuid.UUID(pipeline_run_id),
            market_id=ma["market_id"],
            research_priority=ma.get("research_priority"),
            structural_reason=ma.get("structural_reason"),
            p_market=ma.get("p_market"),
            failed_stages=failed_stages,
        ))
        await db.commit()


async def _analyze_market_simple(
    pipeline_run_id: str,
    prompts: dict,
    ma: MarketAnalysis,
    market_id: str,
    provider: str,
    model: str,
    _call,
    max_tokens: int,
    temperature: float,
) -> dict:
    """Stage 2 simple mode: single LLM agent with web search returns p_yes + confidence + reasoning."""
    from app.graph.prompts import get_simple_agent_system
    from app.models.analysis import Analysis
    from app.database import async_session_factory

    system_prompt = get_simple_agent_system(prompts)

    now_utc = datetime.now(timezone.utc)
    p_market = ma.get("p_market") or 0.5
    resolution_date = ma.get("resolution_date") or "unknown"
    question = ma.get("question", "")
    event_context = (ma.get("event_title") or ma.get("category") or "").strip()

    user_lines = [
        f"Today (UTC): {now_utc.strftime('%Y-%m-%d')}",
        f"Market question: {question}",
        f"Current implied market probability: {p_market:.1%}",
        f"Resolution date: {resolution_date}",
    ]
    if event_context:
        user_lines.append(f"Event context: {event_context}")
    user_prompt = "\n".join(user_lines)

    wsq = stage2_web_search_query(ma)

    await raise_if_pipeline_cancelled(pipeline_run_id)

    raw, dur, meta, inp_tok, out_tok, rc, rr = await _call(
        system_prompt, user_prompt, max_tokens, True, temperature,
        web_search_query=wsq,
    )

    p_yes: float | None = None
    confidence: float | None = None
    reasoning: str | None = None
    err: str | None = None
    parsed: dict | None = None
    try:
        parsed = parse_json_object(raw)
        p_yes_raw = parsed.get("p_yes")
        conf_raw = parsed.get("confidence")
        reasoning = str(parsed.get("reasoning") or "").strip() or None
        if p_yes_raw is not None:
            p_yes = float(p_yes_raw)
            if not (0.0 <= p_yes <= 1.0):
                err = f"p_yes out of range: {p_yes}"
                p_yes = None
        if conf_raw is not None:
            confidence = float(conf_raw)
            confidence = max(0.0, min(1.0, confidence))
    except Exception as exc:
        err = str(exc)[:300]

    await log_llm_call(
        pipeline_run_id, market_id, "simple_agent", provider, model,
        system_prompt, user_prompt, raw, parsed,
        temperature, max_tokens, True, dur, err,
        input_tokens=inp_tok, output_tokens=out_tok,
        retry_count=rc, retry_reason=rr,
    )

    gap = round(p_yes - ma["p_market"], 4) if p_yes is not None and ma.get("p_market") is not None else None
    failed_stages: list[dict] = [{"stage": "simple_agent", "reason": err}] if err else []

    analysis_id = uuid.uuid4()
    async with async_session_factory() as db:
        db.add(Analysis(
            id=analysis_id,
            pipeline_run_id=uuid.UUID(pipeline_run_id),
            market_id=market_id,
            research_priority=ma.get("research_priority"),
            structural_reason=ma.get("structural_reason"),
            evidence_pool=[raw] if raw else [],
            p_yes=p_yes,
            confidence=confidence,
            reasoning=reasoning,
            p_market=ma.get("p_market"),
            gap=gap,
            failed_stages=failed_stages if failed_stages else None,
        ))
        await db.commit()

    completed: MarketAnalysis = {
        **ma,
        "p_yes": p_yes,
        "confidence": confidence,
        "reasoning": reasoning,
        "gap": gap,
        "analysis_db_id": str(analysis_id),
    }
    return {"analyses": [completed]}


async def _analyze_market_inner(
    pipeline_run_id: str,
    config: dict,
    prompts: dict,
    ma: MarketAnalysis,
    market_id: str,
    provider: str,
    model: str,
    temperature: float,
    web: bool,
    mt_news: int,
    mt_base: int,
    mt_debate: int,
    mt_judge: int,
    max_pairs: int,
    convergence_threshold: float,
    _call,
    *,
    t_evidence: float | None = None,
    t_debate: float | None = None,
    t_judge: float | None = None,
) -> dict:
    te = t_evidence if t_evidence is not None else temperature
    td = t_debate if t_debate is not None else temperature
    tj = t_judge if t_judge is not None else temperature
    wsq = stage2_web_search_query(ma)

    now_utc = datetime.now(timezone.utc)
    cutoff = (now_utc - timedelta(days=30)).date()
    failed_stages: list[dict] = []

    # --- Qdrant RAG ---
    rag_block = ""
    try:
        from app.services.qdrant_service import qdrant_service
        similar = await qdrant_service.search_similar(ma["question"], top_k=5)
        rag_block = qdrant_service.format_for_prompt(similar)
    except Exception as exc:
        logger.warning("Qdrant RAG failed for %s: %s", market_id, exc)

    # --- News + Base Rate in parallel ---
    news_sys = prompt_helpers.get_news_system(prompts)
    news_user = (
        f"=== MARKET CONTEXT (blind — no price) ===\n"
        f"Today (UTC): {now_utc.strftime('%Y-%m-%d')}\n"
        f"Event: {ma.get('event_title') or '(none)'}\n"
        f"Market question: {ma['question']}\n"
        f"Description: {ma.get('market_description') or '(none)'}\n"
        f"Category: {ma.get('category') or '(none)'}\n"
        f"Resolution date: {ma.get('resolution_date')}\n"
    )
    base_sys = prompt_helpers.get_base_rate_system(prompts)
    base_user = (
        f"Market question: {ma['question']}\n"
        f"Description: {ma.get('market_description') or '(none)'}\n"
        f"Resolution date: {ma.get('resolution_date')}\n"
        + (f"\n{rag_block}" if rag_block else "")
    )

    news_items: list[dict] = []
    base_items: list[dict] = []

    async def _fetch_news():
        try:
            raw, dur, meta, inp, out, rc, rr = await _call(
                news_sys, news_user, mt_news, web, temp=te, web_search_query=wsq,
            )
            items = parse_json_array(raw)
            await log_llm_call(
                pipeline_run_id, market_id, "news", provider, model,
                news_sys, news_user, raw, items, te, mt_news, web, dur,
                call_metadata=meta if web else None,
                input_tokens=inp, output_tokens=out, retry_count=rc, retry_reason=rr,
            )
            return items
        except Exception as exc:
            failed_stages.append({"stage": "news", "reason": str(exc)[:200]})
            await log_llm_call(pipeline_run_id, market_id, "news", provider, model,
                           news_sys, news_user, "", None, te, mt_news, web, 0.0, str(exc))
            return []

    async def _fetch_base():
        try:
            raw, dur, meta, inp, out, rc, rr = await _call(
                base_sys, base_user, mt_base, web, temp=te, web_search_query=wsq,
            )
            items = parse_json_array(raw)
            await log_llm_call(
                pipeline_run_id, market_id, "baserate", provider, model,
                base_sys, base_user, raw, items, te, mt_base, web, dur,
                call_metadata=meta if web else None,
                input_tokens=inp, output_tokens=out, retry_count=rc, retry_reason=rr,
            )
            return items
        except Exception as exc:
            failed_stages.append({"stage": "base_rate", "reason": str(exc)[:200]})
            await log_llm_call(pipeline_run_id, market_id, "baserate", provider, model,
                           base_sys, base_user, "", None, te, mt_base, web, 0.0, str(exc))
            return []

    news_items, base_items = await asyncio.gather(_fetch_news(), _fetch_base())

    await raise_if_pipeline_cancelled(pipeline_run_id)

    news_lines = format_news_lines(news_items, cutoff)
    base_lines = format_base_rate_lines(base_items)
    pool_str = "\n".join(news_lines + base_lines)

    # --- Debate ---
    q = ma["question"]
    bull_sys = prompt_helpers.get_bull_debate_system(prompts)
    bear_sys = prompt_helpers.get_bear_debate_system(prompts)
    debate_ctx = (
        f"Market question: {q}\n"
        f"Resolution date: {ma.get('resolution_date')}\n\n"
        f"=== EVIDENCE ===\n{pool_str}\n\n"
    )

    transcript_parts: list[str] = []
    debate_messages: list[dict] = []
    debate_history: list[dict] = []
    debate_consensus = False
    debate_stop_reason: str | None = None
    pairs_completed = 0

    for k in range(1, max_pairs + 1):
        await raise_if_pipeline_cancelled(pipeline_run_id)
        history_block = (
            "\n\n".join(transcript_parts)
            if transcript_parts
            else "(Opening round — the Bear has not spoken yet.)"
        )

        # Bull
        bull_user = f"{debate_ctx}=== DEBATE SO FAR ===\n{history_block}\n"
        bull_raw = ""
        bull_dur = 0.0
        bull_inp = bull_out = None
        bull_rc = 0
        bull_rr = None
        bull_parsed = None
        bull_parse_err: str | None = None
        try:
            bull_raw, bull_dur, _, bull_inp, bull_out, bull_rc, bull_rr = await _call(bull_sys, bull_user, mt_debate, False, temp=td)
            bull_parsed, bull_parse_err = parse_debate_control_footer(bull_raw)
        except Exception as exc:
            failed_stages.append({"stage": f"debate_bull_{k}", "reason": str(exc)[:200]})
            bull_parse_err = str(exc)[:100]

        bull_ctrl = normalize_debate_control(bull_parsed)
        bull_meta: dict = {**bull_ctrl, "parse_error": bull_parse_err}
        await log_llm_call(
            pipeline_run_id, market_id, f"debate_bull_{k}", provider, model,
            bull_sys, bull_user, bull_raw, bull_meta, td, mt_debate, False, bull_dur,
            input_tokens=bull_inp, output_tokens=bull_out, retry_count=bull_rc, retry_reason=bull_rr,
        )
        debate_messages.append({"role": "bull", "round": k, "text": bull_raw})
        transcript_parts.append(f"ROUND {k} Bull:\n{strip_debate_footer(bull_raw)}")

        # Bear
        bear_user = f"{debate_ctx}=== DEBATE SO FAR ===\n" + "\n\n".join(transcript_parts) + "\n"
        bear_raw = ""
        bear_dur = 0.0
        bear_inp = bear_out = None
        bear_rc = 0
        bear_rr = None
        bear_parsed = None
        bear_parse_err: str | None = None
        try:
            bear_raw, bear_dur, _, bear_inp, bear_out, bear_rc, bear_rr = await _call(bear_sys, bear_user, mt_debate, False, temp=td)
            bear_parsed, bear_parse_err = parse_debate_control_footer(bear_raw)
        except Exception as exc:
            failed_stages.append({"stage": f"debate_bear_{k}", "reason": str(exc)[:200]})
            bear_parse_err = str(exc)[:100]

        bear_ctrl = normalize_debate_control(bear_parsed)
        bear_meta: dict = {**bear_ctrl, "parse_error": bear_parse_err}
        await log_llm_call(
            pipeline_run_id, market_id, f"debate_bear_{k}", provider, model,
            bear_sys, bear_user, bear_raw, bear_meta, td, mt_debate, False, bear_dur,
            input_tokens=bear_inp, output_tokens=bear_out, retry_count=bear_rc, retry_reason=bear_rr,
        )
        debate_messages.append({"role": "bear", "round": k, "text": bear_raw})
        transcript_parts.append(f"ROUND {k} Bear:\n{strip_debate_footer(bear_raw)}")

        bull_p = bull_ctrl.get("p_yes_estimate")
        bear_p = bear_ctrl.get("p_yes_estimate")
        pairs_completed = k

        converged = (
            bull_p is not None and bear_p is not None
            and abs(bull_p - bear_p) <= convergence_threshold
        )
        debate_history.append({
            "round": k,
            "bull_p_yes_estimate": bull_p,
            "bear_p_yes_estimate": bear_p,
            "converged": converged,
        })
        if converged:
            debate_consensus = True
            debate_stop_reason = "convergence"
            break
    else:
        debate_stop_reason = "max_rounds"

    await raise_if_pipeline_cancelled(pipeline_run_id)

    full_transcript = "\n\n".join(transcript_parts)

    # --- Judge ---
    judge_sys = prompt_helpers.get_judge_system(prompts)
    judge_user = (
        f"Market question: {q}\nResolution date: {ma.get('resolution_date')}\n"
        f"Debate metadata: rounds_completed={pairs_completed}, converged={debate_consensus}, stop_reason={debate_stop_reason}\n\n"
        f"=== EVIDENCE ===\n{pool_str}\n\n"
        f"=== DEBATE (full transcript) ===\n{full_transcript}\n"
    )

    p_yes = confidence = None
    reasoning = ""
    judge_parsed = None
    judge_err = None
    judge_inp = judge_out = None
    judge_rc = 0
    judge_rr = None
    judge_raw = ""
    judge_dur = 0.0

    try:
        judge_raw, judge_dur, _, judge_inp, judge_out, judge_rc, judge_rr = await _call(judge_sys, judge_user, mt_judge, False, temp=tj)
        judge_parsed = parse_json_object(judge_raw)
        p_yes = float(judge_parsed["p_yes"])
        confidence = float(judge_parsed["confidence"])
        reasoning = str(judge_parsed.get("reasoning", "")).strip()
        if not (0 <= p_yes <= 1) or not (0 <= confidence <= 1):
            raise ValueError("p_yes/confidence out of [0,1]")
    except Exception as exc:
        judge_err = str(exc)
        failed_stages.append({"stage": "judge", "reason": judge_err[:200]})
        judge_raw = judge_raw or ""
        judge_dur = judge_dur or 0.0

    await log_llm_call(
        pipeline_run_id, market_id, "judge", provider, model,
        judge_sys, judge_user, judge_raw, judge_parsed,
        tj, mt_judge, False, judge_dur, judge_err,
        input_tokens=judge_inp, output_tokens=judge_out, retry_count=judge_rc, retry_reason=judge_rr,
    )

    gap = round(p_yes - ma["p_market"], 4) if p_yes is not None else None

    # --- Save analysis row ---
    analysis_id = uuid.uuid4()
    from app.models.analysis import Analysis
    from app.database import async_session_factory
    async with async_session_factory() as db:
        db.add(Analysis(
            id=analysis_id,
            pipeline_run_id=uuid.UUID(pipeline_run_id),
            market_id=market_id,
            research_priority=ma.get("research_priority"),
            structural_reason=ma.get("structural_reason"),
            evidence_pool=news_lines + base_lines,
            p_yes=p_yes,
            confidence=confidence,
            reasoning=reasoning,
            p_market=ma["p_market"],
            gap=gap,
            debate_pairs_completed=pairs_completed,
            debate_consensus=debate_consensus,
            debate_stop_reason=debate_stop_reason,
            debate_history=debate_history,
            failed_stages=failed_stages if failed_stages else None,
        ))
        await db.commit()

    completed: MarketAnalysis = {
        **ma,
        "news_evidence": news_items,
        "base_rate_evidence": base_items,
        "evidence_pool": news_lines + base_lines,
        "debate_messages": debate_messages,
        "debate_pairs_completed": pairs_completed,
        "debate_consensus": debate_consensus,
        "debate_stop_reason": debate_stop_reason,
        "debate_history": debate_history,
        "p_yes": p_yes,
        "confidence": confidence,
        "reasoning": reasoning,
        "gap": gap,
        "analysis_db_id": str(analysis_id),
        "failed_stages": failed_stages if failed_stages else None,
    }
    return {"analyses": [completed]}
