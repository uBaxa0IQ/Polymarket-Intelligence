from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from sqlalchemy import select

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_ROOT = os.path.dirname(SCRIPT_DIR)
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.database import async_session_factory
from app.models.market import Market


def _parse_iso_datetime(raw: object) -> datetime | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _fetch_markets_page(base_url: str, limit: int, offset: int, timeout: float) -> list[dict]:
    params = {
        "limit": str(limit),
        "offset": str(offset),
    }
    url = f"{base_url.rstrip('/')}/markets?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url=url, headers={"User-Agent": "poly-backfill-end-date/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError("Unexpected Gamma response (expected list)")
    return [x for x in data if isinstance(x, dict)]


async def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill markets.end_date from Polymarket Gamma API.")
    parser.add_argument("--base-url", default="https://gamma-api.polymarket.com", help="Gamma API base URL")
    parser.add_argument("--page-size", type=int, default=500, help="Page size for Gamma pagination")
    parser.add_argument("--max-pages", type=int, default=200, help="Safety cap for pages to fetch")
    parser.add_argument("--timeout-sec", type=float, default=30.0, help="HTTP timeout per request")
    parser.add_argument("--dry-run", action="store_true", help="Only print what would be updated")
    args = parser.parse_args()

    async with async_session_factory() as db:
        res = await db.execute(select(Market.market_id).where(Market.end_date.is_(None)))
        missing_ids = {str(mid) for (mid,) in res.all() if mid}

    if not missing_ids:
        print("No rows with NULL end_date found. Nothing to do.")
        return

    print(f"Rows with NULL end_date: {len(missing_ids)}")
    print("Fetching Gamma markets pages...")

    fetched = 0
    offset = 0
    matches: dict[str, datetime] = {}
    for page_num in range(1, args.max_pages + 1):
        page = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _fetch_markets_page(
                base_url=args.base_url,
                limit=args.page_size,
                offset=offset,
                timeout=args.timeout_sec,
            ),
        )
        if not page:
            break

        fetched += len(page)
        for row in page:
            market_id = row.get("id")
            if market_id is None:
                continue
            market_id = str(market_id)
            if market_id not in missing_ids:
                continue
            end_dt = _parse_iso_datetime(row.get("endDate"))
            if end_dt is not None:
                matches[market_id] = end_dt

        print(f"Page {page_num}: fetched={len(page)}, matched={len(matches)}")
        if len(matches) >= len(missing_ids):
            break
        if len(page) < args.page_size:
            break
        offset += len(page)

    if not matches:
        print("No matching endDate values found in fetched Gamma pages.")
        print("Tip: increase --max-pages or adjust --base-url.")
        return

    print(f"Found end_date for {len(matches)} markets out of {len(missing_ids)} missing.")
    if args.dry_run:
        print("Dry-run mode: database was not changed.")
        return

    updated = 0
    async with async_session_factory() as db:
        res = await db.execute(
            select(Market).where(
                Market.market_id.in_(list(matches.keys())),
                Market.end_date.is_(None),
            )
        )
        rows = res.scalars().all()
        for m in rows:
            dt = matches.get(m.market_id)
            if dt is None:
                continue
            m.end_date = dt
            updated += 1
        await db.commit()

    print(f"Done. Updated {updated} rows. Fetched Gamma records: {fetched}.")


if __name__ == "__main__":
    asyncio.run(main())
