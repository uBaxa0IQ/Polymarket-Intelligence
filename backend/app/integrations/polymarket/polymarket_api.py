"""Polymarket Gamma API — fetch and filter markets.

Ported from pm_screener.py (logic preserved verbatim).
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@dataclass
class ScreenStats:
    markets_seen: int = 0
    skip_whitelist: int = 0
    skip_blacklist: int = 0
    skip_min_volume: int = 0
    skip_max_volume: int = 0
    skip_no_end_date: int = 0
    skip_hours_below_min: int = 0
    skip_hours_above_max: int = 0
    skip_hopeless_odds: int = 0
    passed: int = 0

    def validate(self) -> None:
        total_out = (
            self.skip_whitelist + self.skip_blacklist + self.skip_min_volume
            + self.skip_max_volume + self.skip_no_end_date + self.skip_hours_below_min
            + self.skip_hours_above_max + self.skip_hopeless_odds + self.passed
        )
        if total_out != self.markets_seen:
            raise RuntimeError(f"ScreenStats mismatch: seen={self.markets_seen}, accounted={total_out}")


# ---------------------------------------------------------------------------
# Gamma API fetch
# ---------------------------------------------------------------------------


async def _fetch_events_page(
    client: httpx.AsyncClient,
    base_url: str,
    params: dict[str, str],
    user_agent: str,
    max_retries: int,
) -> list[dict[str, Any]]:
    """One paginated GET with retries on network/TLS errors and some HTTP statuses."""
    base = base_url.rstrip("/")
    headers = {"User-Agent": user_agent}
    last_err: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            r = await client.get(base, params=params, headers=headers)
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, list):
                raise ValueError("Unexpected API response (expected list)")
            return data
        except ValueError:
            raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in _RETRYABLE_STATUS_CODES:
                raise
            last_err = exc
        except httpx.RequestError as exc:
            last_err = exc

        if last_err is not None and attempt < max_retries:
            wait = min(2.0**attempt, 60.0)
            logger.warning(
                "Gamma API page fetch attempt %d/%d failed: %s; retrying in %.1fs",
                attempt,
                max_retries,
                last_err,
                wait,
            )
            await asyncio.sleep(wait)
        elif last_err is not None:
            raise last_err

    raise RuntimeError("unreachable")  # pragma: no cover


async def fetch_open_events(
    base_url: str = "https://gamma-api.polymarket.com/events",
    limit: int = 5000,
    user_agent: str = "pm-screener-v1/1.0",
    timeout: float = 30.0,
    max_retries: int = 3,
) -> list[dict[str, Any]]:
    if limit <= 0:
        return []

    per_page = min(limit, 500)
    offset = 0
    collected: list[dict[str, Any]] = []
    t = httpx.Timeout(timeout)
    async with httpx.AsyncClient(timeout=t, follow_redirects=True) as client:
        while len(collected) < limit:
            batch_limit = min(per_page, limit - len(collected))
            params = {
                "active": "true",
                "closed": "false",
                "limit": str(batch_limit),
                "offset": str(offset),
                "order": "volume",
                "ascending": "false",
            }
            data = await _fetch_events_page(
                client, base_url, params, user_agent, max_retries
            )
            if not data:
                break
            collected.extend(data)
            offset += len(data)
            if len(data) < batch_limit:
                break

    return collected[:limit]


# ---------------------------------------------------------------------------
# Tag / volume / time helpers
# ---------------------------------------------------------------------------

def _parse_str_list(raw: Any) -> list[Any]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            d = json.loads(raw)
            return d if isinstance(d, list) else []
        except json.JSONDecodeError:
            return []
    return []


def get_market_tags(obj: dict[str, Any]) -> set[str]:
    slugs: set[str] = set()
    for tag in _parse_str_list(obj.get("tags")):
        if isinstance(tag, dict):
            v = tag.get("slug") or tag.get("name") or tag.get("label")
            if isinstance(v, str):
                slugs.add(v.strip().lower())
        elif isinstance(tag, str):
            slugs.add(tag.strip().lower())
    cat = obj.get("category")
    if isinstance(cat, str):
        slugs.add(cat.strip().lower())
    return slugs


async def fetch_open_positions(
    wallet_address: str,
    base_url: str = "https://gamma-api.polymarket.com",
    timeout: float = 15.0,
) -> set[str]:
    """Return lowercase condition_ids of markets where wallet has an open position (size > 0)."""
    url = f"{base_url.rstrip('/')}/positions"
    params = {"user": wallet_address, "sizeThreshold": "0.01"}
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url, params=params, headers={"User-Agent": "pm-intelligence-v2/1.0"})
        r.raise_for_status()
        data = r.json()

    condition_ids: set[str] = set()
    for pos in data or []:
        cid = pos.get("conditionId") or pos.get("condition_id") or ""
        raw_size = pos.get("size") or pos.get("currentValue") or pos.get("value") or 0
        try:
            size = float(raw_size)
        except (TypeError, ValueError):
            size = 0.0
        if cid and size > 0:
            condition_ids.add(str(cid).lower())
    return condition_ids


def effective_tags(event: dict, market: dict) -> set[str]:
    return get_market_tags(event) | get_market_tags(market)


def get_volume(market: dict[str, Any]) -> float:
    vol = market.get("volumeNum") or market.get("volume") or 0
    try:
        return float(vol)
    except (ValueError, TypeError):
        return 0.0


def get_yes_no_implied(market: dict[str, Any]) -> tuple[float | None, float | None]:
    outcomes = _parse_str_list(market.get("outcomes"))
    prices_raw = _parse_str_list(market.get("outcomePrices"))
    if len(outcomes) != len(prices_raw) or len(outcomes) < 2:
        return None, None
    try:
        prices = [float(p) for p in prices_raw]
    except (TypeError, ValueError):
        return None, None
    labels = [str(o).strip().lower() for o in outcomes]
    yes_i = no_i = None
    for i, lab in enumerate(labels):
        if lab in ("yes", "y"):
            yes_i = i
        elif lab in ("no", "n"):
            no_i = i
    if yes_i is None or no_i is None:
        if len(outcomes) == 2:
            yes_i, no_i = 0, 1
        else:
            return None, None
    try:
        return prices[yes_i], prices[no_i]
    except IndexError:
        return None, None


def get_hours_left(obj: dict[str, Any]) -> float | None:
    end_str = obj.get("endDate")
    if not end_str:
        return None
    try:
        end_str = str(end_str).replace("Z", "+00:00")
        end_dt = datetime.fromisoformat(end_str)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        delta = end_dt - datetime.now(timezone.utc)
        return delta.total_seconds() / 3600.0
    except Exception:
        return None


def effective_hours_left(event: dict, market: dict) -> float | None:
    h = get_hours_left(market)
    if h is None:
        h = get_hours_left(event)
    return h


# ---------------------------------------------------------------------------
# Filter chain
# ---------------------------------------------------------------------------

def screen_events(
    events: list[dict[str, Any]],
    tag_whitelist: set[str],
    tag_blacklist: set[str],
    min_volume: float,
    max_volume: float | None,
    min_hours: float,
    max_hours: float,
    min_underdog_implied: float | None,
) -> tuple[list[dict[str, Any]], ScreenStats]:
    out: list[dict[str, Any]] = []
    stats = ScreenStats()

    for event in events:
        if not isinstance(event, dict):
            continue
        markets = event.get("markets")
        if not isinstance(markets, list):
            continue
        for market in markets:
            if not isinstance(market, dict):
                continue
            if not market.get("active") or market.get("closed"):
                continue

            stats.markets_seen += 1
            tags = effective_tags(event, market)

            # Whitelist
            if tag_whitelist and not (tags & tag_whitelist):
                stats.skip_whitelist += 1
                continue

            # Blacklist
            if tag_blacklist and (tags & tag_blacklist):
                stats.skip_blacklist += 1
                continue

            # Volume
            vol = get_volume(market)
            if vol < min_volume:
                stats.skip_min_volume += 1
                continue
            if max_volume is not None and vol > max_volume:
                stats.skip_max_volume += 1
                continue

            # Hours
            hours = effective_hours_left(event, market)
            if hours is None:
                stats.skip_no_end_date += 1
                continue
            if hours < min_hours:
                stats.skip_hours_below_min += 1
                continue
            if hours > max_hours:
                stats.skip_hours_above_max += 1
                continue

            # Underdog
            y_impl, n_impl = get_yes_no_implied(market)
            if min_underdog_implied is not None and y_impl is not None and n_impl is not None:
                if min(y_impl, n_impl) < min_underdog_implied:
                    stats.skip_hopeless_odds += 1
                    continue

            stats.passed += 1
            tags_all = sorted(tags)
            out.append({
                "event_id": event.get("id"),
                "market_id": market.get("id"),
                "condition_id": market.get("conditionId"),
                "event_title": event.get("title"),
                "event_slug": event.get("slug"),
                "question": market.get("question"),
                "market_slug": market.get("slug"),
                "market_description": market.get("description") or event.get("description") or "",
                "volume": vol,
                "hours_left": hours,
                "tags_all": tags_all,
                "tags_matched": sorted(tags & tag_whitelist) if tag_whitelist else tags_all,
                "endDate": market.get("endDate") or event.get("endDate"),
                "yes_implied": y_impl,
                "no_implied": n_impl,
            })

    stats.validate()
    out.sort(key=lambda r: (-r["volume"], r["hours_left"]))
    return out, stats
