"""Stage 1a: Gamma screener node."""
from __future__ import annotations

import logging

from app.graph.pipeline_persistence import raise_if_pipeline_cancelled, update_pipeline_run
from app.graph.state import PipelineState

logger = logging.getLogger(__name__)

# Stage 1a: screen_markets
# ---------------------------------------------------------------------------

async def screen_markets(state: PipelineState) -> dict:
    config = state["config"]
    sc = config.get("screener", {})
    await raise_if_pipeline_cancelled(state["pipeline_run_id"])
    await update_pipeline_run(state["pipeline_run_id"], current_stage="screener")

    from app.integrations.polymarket.polymarket_api import fetch_open_events, screen_events

    events = await fetch_open_events(
        base_url=sc.get("gamma_api_base", "https://gamma-api.polymarket.com/events"),
        limit=int(sc.get("limit", 5000)),
        user_agent="pm-intelligence-v2/1.0",
        timeout=float(sc.get("request_timeout_sec", 30)),
    )

    await raise_if_pipeline_cancelled(state["pipeline_run_id"])

    wl = {str(x).strip().lower() for x in (sc.get("tag_whitelist") or []) if str(x).strip()}
    bl = {str(x).strip().lower() for x in (sc.get("tag_blacklist") or []) if str(x).strip()}

    rows, stats = screen_events(
        events=events,
        tag_whitelist=wl,
        tag_blacklist=bl,
        min_volume=float(sc.get("min_volume", 5000)),
        max_volume=sc.get("max_volume"),
        min_hours=float(sc.get("min_hours", 24)),
        max_hours=float(sc.get("max_hours", 96)),
        min_underdog_implied=sc.get("min_underdog_implied", 0.1),
    )

    # Filter out markets where the wallet already has an open external position
    skip_open_position = 0
    open_pos_market_ids: set[str] = set()
    if sc.get("exclude_open_positions", True):
        try:
            from app.clob.client import get_clob_client
            from app.integrations.polymarket.polymarket_api import fetch_open_positions

            clob = get_clob_client(config)
            if clob:
                wallet = clob.get_address()
                if wallet:
                    open_condition_ids = await fetch_open_positions(
                        wallet_address=wallet,
                        timeout=float(sc.get("request_timeout_sec", 30)),
                    )
                    if open_condition_ids:
                        filtered: list[dict] = []
                        for r in rows:
                            cid = str(r.get("condition_id") or "").lower()
                            if cid and cid in open_condition_ids:
                                skip_open_position += 1
                                open_pos_market_ids.add(r["market_id"])
                            else:
                                filtered.append(r)
                        rows = filtered
                        if skip_open_position:
                            logger.info(
                                "Excluded %d market(s) with open external positions", skip_open_position
                            )
        except Exception as exc:
            logger.warning("Could not fetch open positions for exclusion: %s", exc)

    # Build screener_results with per-market filter reasons
    all_markets_data = []
    passed_ids = {r["market_id"] for r in rows}

    for ev in events:
        for market in (ev.get("markets") or [ev]):
            mid = str(market.get("id") or market.get("market_id") or "")
            if not mid:
                continue
            if mid in passed_ids:
                passed = True
                reason = None
            elif mid in open_pos_market_ids:
                passed = False
                reason = "open_position"
            else:
                passed = False
                reason = _screener_filter_reason({**market, "_event": ev}, sc, wl, bl)
            all_markets_data.append({
                "id": mid,
                "question": str(market.get("question") or market.get("title") or ""),
                "volume": market.get("volume") or market.get("volumeNum") or 0,
                "passed": passed,
                "filter_reason": reason,
            })

    screener_results = {
        "total_fetched": len(all_markets_data),
        "total_passed": len(rows),
        "stats": {
            "markets_seen": stats.markets_seen,
            "skip_whitelist": stats.skip_whitelist,
            "skip_blacklist": stats.skip_blacklist,
            "skip_min_volume": stats.skip_min_volume,
            "skip_max_volume": stats.skip_max_volume,
            "skip_no_end_date": stats.skip_no_end_date,
            "skip_hours_below_min": stats.skip_hours_below_min,
            "skip_hours_above_max": stats.skip_hours_above_max,
            "skip_hopeless_odds": stats.skip_hopeless_odds,
            "skip_open_position": skip_open_position,
            "passed": stats.passed - skip_open_position,
        },
        "markets": all_markets_data,
    }

    await update_pipeline_run(
        state["pipeline_run_id"],
        markets_screened=stats.passed,
        screener_results=screener_results,
    )
    return {"screened_markets": rows}


def _screener_filter_reason(market: dict, sc: dict, wl: set, bl: set) -> str:
    """Determine why a market was filtered out."""
    from app.integrations.polymarket.polymarket_api import (
        effective_hours_left,
        effective_tags,
        get_volume,
        get_yes_no_implied,
    )

    # market in this context can be either a market row or event-like wrapper.
    event = market.get("_event") if isinstance(market.get("_event"), dict) else market
    tags = effective_tags(event, market)
    if bl and (tags & bl):
        return "tag_blacklisted"
    if wl and not (tags & wl):
        return "tag_not_whitelisted"

    vol = get_volume(market)
    min_vol = float(sc.get("min_volume", 5000))
    max_vol = sc.get("max_volume")
    if vol < min_vol:
        return "volume_too_low"
    if max_vol and vol > float(max_vol):
        return "volume_too_high"

    min_hours = float(sc.get("min_hours", 24))
    max_hours = float(sc.get("max_hours", 96))
    hours_left = effective_hours_left(event, market)
    if hours_left is None:
        return "no_end_date"
    if hours_left < min_hours:
        return "hours_below_min"
    if hours_left > max_hours:
        return "hours_above_max"

    min_underdog_implied = sc.get("min_underdog_implied", 0.1)
    if min_underdog_implied is not None:
        y_impl, n_impl = get_yes_no_implied(market)
        if y_impl is not None and n_impl is not None and min(y_impl, n_impl) < float(min_underdog_implied):
            return "hopeless_odds"

    return "other_filter"

