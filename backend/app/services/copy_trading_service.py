from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import uuid
from typing import Any

from app.database import async_session_factory
from app.integrations.polymarket.polymarket_data_api import fetch_positions_value_usd
from app.services.settings_service import settings_service
from sqlalchemy import select

logger = logging.getLogger(__name__)

DATA_API_BASE = "https://data-api.polymarket.com"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        s = value.strip().lower()
        if s in {"true", "1", "yes", "on"}:
            return True
        if s in {"false", "0", "no", "off"}:
            return False
    if value is None:
        return default
    return bool(value)


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _parse_activity_timestamp(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        ts = float(value)
        # Handle possible milliseconds timestamps.
        if ts > 10_000_000_000:
            ts = ts / 1000.0
        return ts if ts > 0 else None
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip()
    if s.isdigit():
        ts = float(s)
        return ts if ts > 0 else None
    # Data API can return UTC timestamps with trailing Z.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _http_get_json(url: str, timeout: float = 20.0, retries: int = 3) -> Any:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "pm-intel-copy-trader/1.0", "Accept": "application/json"},
    )
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            last_err = exc
            if attempt < retries:
                time.sleep(min(2**attempt, 5))
    raise RuntimeError(f"Request failed: {url} ({last_err})")


def _build_event_id(a: dict[str, Any]) -> str:
    tx = str(a.get("transactionHash") or "no_tx")
    asset = str(a.get("asset") or "no_asset")
    ts = str(a.get("timestamp") or "no_ts")
    side = str(a.get("side") or "no_side")
    return f"{tx}|{asset}|{ts}|{side}"


def _parse_copy_side(row: dict[str, Any], binary_only: bool) -> str | None:
    outcome = str(row.get("outcome") or "").strip().lower()
    if outcome in ("yes", "y"):
        return "yes"
    if outcome in ("no", "n"):
        return "no"
    # For safety, do not infer non-explicit yes/no when binary_only is on.
    if binary_only:
        return None
    idx = row.get("outcomeIndex")
    if idx in (0, "0"):
        return "yes"
    if idx in (1, "1"):
        return "no"
    return None


def _parse_collateral_balance_usd(raw: dict[str, Any] | None) -> float | None:
    if not raw:
        return None
    try:
        return float(raw.get("balance")) / 1_000_000.0
    except (TypeError, ValueError):
        return None


@dataclass
class CopySignal:
    event_id: str
    source_wallet: str
    source_timestamp: float | None
    condition_id: str
    side: str
    title: str
    source_price: float | None
    source_usdc_size: float | None


class CopyTradingService:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._processed_ids: set[str] = set()
        self._processed_queue: deque[str] = deque(maxlen=30000)
        self._recent_events: deque[dict[str, Any]] = deque(maxlen=300)
        self._orders_timestamps: deque[float] = deque(maxlen=10000)
        self._last_loop_at: str | None = None
        self._last_error: str | None = None
        self._last_signals_count: int = 0
        self._is_running: bool = False
        self._warmed_wallets: set[str] = set()
        self._next_check_at_ts: float | None = None
        self._target_stats_cache: dict[str, dict[str, Any]] = {}
        self._wallet_runtime: dict[str, dict[str, Any]] = {}

    def _remember_processed(self, event_id: str) -> None:
        if event_id in self._processed_ids:
            return
        if len(self._processed_queue) == self._processed_queue.maxlen:
            oldest = self._processed_queue[0]
            self._processed_ids.discard(oldest)
        self._processed_queue.append(event_id)
        self._processed_ids.add(event_id)

    def _log_event(self, level: str, message: str, **extra: Any) -> None:
        row = {"ts": _now_iso(), "level": level, "message": message, **extra}
        self._recent_events.appendleft(row)
        if level in {"error", "warn"}:
            logger.warning("copy-trading: %s | %s", message, extra)
        else:
            logger.info("copy-trading: %s | %s", message, extra)

    def _wallet_state(self, wallet: str) -> dict[str, Any]:
        w = wallet.lower()
        state = self._wallet_runtime.get(w)
        if state is None:
            state = {
                "copied_count": 0,
                "skipped_count": 0,
                "skip_reasons": {},
                "last_fetch_ok_at": None,
                "last_fetch_error": None,
                "last_fetch_error_at": None,
                "fetch_error_streak": 0,
                "backoff_until_ts": 0.0,
            }
            self._wallet_runtime[w] = state
        return state

    def _mark_fetch_success(self, wallet: str) -> None:
        st = self._wallet_state(wallet)
        st["last_fetch_ok_at"] = _now_iso()
        st["last_fetch_error"] = None
        st["last_fetch_error_at"] = None
        st["fetch_error_streak"] = 0
        st["backoff_until_ts"] = 0.0

    def _mark_fetch_error(self, wallet: str, error: str) -> None:
        st = self._wallet_state(wallet)
        streak = int(st.get("fetch_error_streak") or 0) + 1
        st["fetch_error_streak"] = streak
        st["last_fetch_error"] = error
        st["last_fetch_error_at"] = _now_iso()
        # Mild exponential backoff to avoid hammering failing wallets.
        st["backoff_until_ts"] = time.time() + min(60.0, float(2**min(streak, 6)))

    def _mark_copied(self, wallet: str) -> None:
        st = self._wallet_state(wallet)
        st["copied_count"] = int(st.get("copied_count") or 0) + 1

    def _mark_skipped(self, wallet: str, reason: str) -> None:
        st = self._wallet_state(wallet)
        st["skipped_count"] = int(st.get("skipped_count") or 0) + 1
        reasons = st.get("skip_reasons") or {}
        reasons[reason] = int(reasons.get(reason) or 0) + 1
        st["skip_reasons"] = reasons

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop(), name="copy-trading-loop")
        self._is_running = True
        self._log_event("info", "copy trading worker started")

    async def stop(self) -> None:
        self._is_running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        self._log_event("info", "copy trading worker stopped")

    async def _load_cfg(self) -> dict[str, Any]:
        async with async_session_factory() as db:
            all_cfg = await settings_service.get_all_as_dict(db)
        return all_cfg

    async def _fetch_activity(self, target_wallet: str, limit: int) -> list[dict[str, Any]]:
        q = urllib.parse.urlencode({"user": target_wallet, "limit": max(1, min(limit, 500))})
        data = await asyncio.to_thread(_http_get_json, f"{DATA_API_BASE}/activity?{q}")
        return data if isinstance(data, list) else []

    @staticmethod
    def _scoped_event_id(source_wallet: str, event_id: str) -> str:
        return f"{source_wallet.lower()}::{event_id}"

    @staticmethod
    def _parse_target_wallets(copy_cfg: dict[str, Any]) -> list[str]:
        out: list[str] = []
        raw_list = copy_cfg.get("target_wallets")
        if isinstance(raw_list, list):
            for row in raw_list:
                w = str(row or "").strip().lower()
                if w.startswith("0x") and len(w) == 42 and w not in out:
                    out.append(w)
        legacy = str(copy_cfg.get("target_wallet") or "").strip().lower()
        if legacy.startswith("0x") and len(legacy) == 42 and legacy not in out:
            out.append(legacy)
        return out

    async def _fetch_activity_all(self, target_wallet: str) -> list[dict[str, Any]]:
        page_limit = 500
        offset = 0
        out: list[dict[str, Any]] = []
        # Safety cap to avoid endless loops on upstream anomalies.
        for _ in range(200):
            q = urllib.parse.urlencode({"user": target_wallet, "limit": page_limit, "offset": offset})
            url = f"{DATA_API_BASE}/activity?{q}"
            try:
                chunk = await asyncio.to_thread(_http_get_json, url)
            except RuntimeError as exc:
                # Data API may return 400 on very high offsets; treat as natural pagination end.
                if "HTTP Error 400" in str(exc):
                    break
                raise
            if not isinstance(chunk, list) or not chunk:
                break
            out.extend(chunk)
            if len(chunk) < page_limit:
                break
            offset += page_limit
        return out

    async def _fetch_open_positions_all(self, target_wallet: str) -> list[dict[str, Any]]:
        page_limit = 500
        offset = 0
        out: list[dict[str, Any]] = []
        # Safety cap: up to 100k rows
        for _ in range(200):
            q = urllib.parse.urlencode({"user": target_wallet, "limit": page_limit, "offset": offset})
            url = f"{DATA_API_BASE}/positions?{q}"
            try:
                chunk = await asyncio.to_thread(_http_get_json, url)
            except RuntimeError as exc:
                # Data API can return 400 on high offsets/end of range.
                if "HTTP Error 400" in str(exc):
                    break
                raise
            if not isinstance(chunk, list) or not chunk:
                break
            out.extend(chunk)
            if len(chunk) < page_limit:
                break
            offset += page_limit
        return out

    def _extract_signals(
        self,
        activity: list[dict[str, Any]],
        *,
        source_wallet: str,
        binary_only: bool,
    ) -> list[CopySignal]:
        out: list[CopySignal] = []
        for row in activity:
            eid = _build_event_id(row)
            scoped_eid = self._scoped_event_id(source_wallet, eid)
            if scoped_eid in self._processed_ids:
                continue
            if str(row.get("type") or "").upper() != "TRADE":
                continue
            if str(row.get("side") or "").upper() != "BUY":
                continue
            cid = str(row.get("conditionId") or "").strip()
            if not cid:
                continue
            side = _parse_copy_side(row, binary_only=binary_only)
            if side is None:
                self._remember_processed(scoped_eid)
                self._mark_skipped(source_wallet, "unsupported_outcome")
                self._log_event(
                    "warn",
                    "skipped non-binary or unsupported outcome",
                    source_wallet=source_wallet,
                    condition_id=cid,
                    title=str(row.get("title") or row.get("slug") or ""),
                )
                continue
            price = _safe_float(row.get("price"), default=float("nan"))
            source_price = None if price != price else price
            out.append(
                CopySignal(
                    event_id=scoped_eid,
                    source_wallet=source_wallet,
                    source_timestamp=_parse_activity_timestamp(row.get("timestamp")),
                    condition_id=cid,
                    side=side,
                    title=str(row.get("title") or row.get("slug") or cid),
                    source_price=source_price,
                    source_usdc_size=_safe_float(row.get("usdcSize"), default=float("nan")),
                )
            )
        out.reverse()
        return out

    async def _run_loop(self) -> None:
        consecutive_errors = 0
        while True:
            try:
                cfg_all = await self._load_cfg()
                c = cfg_all.get("copytrading") or {}
                betting_cfg = cfg_all.get("betting") or {}
                risk_cfg = cfg_all.get("risk") or {}

                enabled = _as_bool(c.get("enabled"), False)
                target_wallets = self._parse_target_wallets(c)
                poll_seconds = max(2.0, float(c.get("poll_seconds") or 10.0))
                activity_limit = int(c.get("activity_limit") or 200)
                live = _as_bool(c.get("live"), False)
                binary_only = _as_bool(c.get("binary_only"), True)
                min_bet_usd = float(c.get("min_bet_usd") or 1.0)
                stake_mode = str(c.get("stake_mode") or "fixed").strip().lower()
                stake_balance_pct = float(c.get("stake_balance_pct") or 0.01)
                stake_trader_ratio = float(c.get("stake_trader_ratio") or 0.01)
                slippage = float(c.get("slippage") or 0.03)
                slippage_protection_enabled = _as_bool(c.get("slippage_protection_enabled"), False)
                max_orders_per_hour = int(c.get("max_orders_per_hour") or 120)
                min_balance_buffer_usd = float(c.get("min_balance_buffer_usd") or 3.0)
                ignore_existing_on_start = _as_bool(c.get("ignore_existing_on_start"), True)

                self._last_loop_at = _now_iso()

                if not enabled:
                    self._next_check_at_ts = time.time() + min(poll_seconds, 10.0)
                    await asyncio.sleep(min(poll_seconds, 10.0))
                    consecutive_errors = 0
                    continue

                if not target_wallets:
                    self._log_event("error", "no valid target wallets in settings")
                    self._next_check_at_ts = time.time() + min(poll_seconds, 10.0)
                    await asyncio.sleep(min(poll_seconds, 10.0))
                    continue

                signals: list[CopySignal] = []
                warmed_any = False
                for target_wallet in target_wallets:
                    st = self._wallet_state(target_wallet)
                    backoff_until = float(st.get("backoff_until_ts") or 0.0)
                    if backoff_until > time.time():
                        self._mark_skipped(target_wallet, "wallet_backoff")
                        continue
                    try:
                        activity = await self._fetch_activity(target_wallet, activity_limit)
                        self._mark_fetch_success(target_wallet)
                    except Exception as exc:
                        self._mark_fetch_error(target_wallet, str(exc))
                        self._mark_skipped(target_wallet, "activity_fetch_error")
                        self._log_event(
                            "warn",
                            "wallet activity fetch failed",
                            source_wallet=target_wallet,
                            error=str(exc),
                        )
                        continue
                    if ignore_existing_on_start and target_wallet not in self._warmed_wallets:
                        for row in activity:
                            scoped_eid = self._scoped_event_id(target_wallet, _build_event_id(row))
                            self._remember_processed(scoped_eid)
                        self._warmed_wallets.add(target_wallet)
                        warmed_any = True
                        self._log_event(
                            "info",
                            "warm-up completed; existing activity ignored",
                            ignored_events=len(activity),
                            source_wallet=target_wallet,
                        )
                        continue
                    signals.extend(self._extract_signals(activity, source_wallet=target_wallet, binary_only=binary_only))
                if warmed_any:
                    self._last_signals_count = 0
                    self._next_check_at_ts = time.time() + poll_seconds
                    await asyncio.sleep(poll_seconds)
                    continue
                signals.sort(key=lambda x: (x.source_timestamp or 0.0, x.event_id))
                conflict_map: dict[str, set[str]] = {}
                source_portfolio_cache: dict[str, float | None] = {}
                for sig in signals:
                    conflict_map.setdefault(sig.condition_id, set()).add(sig.side)
                conflicted_conditions = {k for k, v in conflict_map.items() if len(v) > 1}
                if conflicted_conditions:
                    for cid in conflicted_conditions:
                        self._log_event("warn", "conflicting signals skipped", condition_id=cid)
                    for s in signals:
                        if s.condition_id in conflicted_conditions:
                            self._mark_skipped(s.source_wallet, "conflicting_signal")
                    signals = [s for s in signals if s.condition_id not in conflicted_conditions]
                self._last_signals_count = len(signals)
                if not signals:
                    self._next_check_at_ts = time.time() + poll_seconds
                    await asyncio.sleep(poll_seconds)
                    consecutive_errors = 0
                    continue

                # prune timestamps outside 1h window
                now_ts = time.time()
                while self._orders_timestamps and now_ts - self._orders_timestamps[0] >= 3600:
                    self._orders_timestamps.popleft()

                live_allowed = live and _as_bool(betting_cfg.get("execution_enabled"), False) and not _as_bool(
                    risk_cfg.get("execution_kill_switch"), False
                )
                clob = None
                if stake_mode in {"balance_pct", "follow_trader_bank_pct"} or live_allowed:
                    from app.clob.client import get_clob_client

                    clob = await asyncio.to_thread(get_clob_client, cfg_all)
                    if live_allowed and clob is None:
                        self._log_event("error", "live mode enabled but CLOB client is unavailable")
                        live_allowed = False

                for sig in signals:
                    self._remember_processed(sig.event_id)

                    if len(self._orders_timestamps) >= max_orders_per_hour:
                        self._mark_skipped(sig.source_wallet, "hourly_order_limit")
                        self._log_event(
                            "warn",
                            "hourly order limit reached, signal skipped",
                            source_wallet=sig.source_wallet,
                            condition_id=sig.condition_id,
                        )
                        continue

                    if sig.source_price is None:
                        self._mark_skipped(sig.source_wallet, "missing_source_price")
                        self._log_event(
                            "warn",
                            "missing source price, signal skipped",
                            source_wallet=sig.source_wallet,
                            condition_id=sig.condition_id,
                        )
                        continue

                    bal_usd = None
                    available_usd = None
                    if clob is not None:
                        bal_raw = await asyncio.to_thread(clob.get_collateral_balance_allowance)
                        bal_usd = _parse_collateral_balance_usd(bal_raw)
                        if bal_usd is not None:
                            available_usd = max(0.0, bal_usd - min_balance_buffer_usd)
                    amount_usd = min_bet_usd
                    if stake_mode == "balance_pct":
                        if available_usd is None:
                            self._mark_skipped(sig.source_wallet, "balance_unavailable_balance_pct")
                            self._log_event(
                                "warn",
                                "balance_pct mode requires readable clob balance, signal skipped",
                                source_wallet=sig.source_wallet,
                                condition_id=sig.condition_id,
                            )
                            continue
                        amount_usd = max(min_bet_usd, available_usd * max(0.0, stake_balance_pct))
                    elif stake_mode == "follow_trader_size":
                        source_size = sig.source_usdc_size
                        if source_size is None or source_size != source_size:
                            self._mark_skipped(sig.source_wallet, "missing_source_size")
                            self._log_event(
                                "warn",
                                "missing source usdcSize for follow_trader_size mode",
                                source_wallet=sig.source_wallet,
                                condition_id=sig.condition_id,
                            )
                            continue
                        amount_usd = max(min_bet_usd, source_size * max(0.0, stake_trader_ratio))
                    elif stake_mode == "follow_trader_bank_pct":
                        if available_usd is None:
                            self._mark_skipped(sig.source_wallet, "balance_unavailable_bank_pct")
                            self._log_event(
                                "warn",
                                "follow_trader_bank_pct mode requires readable clob balance, signal skipped",
                                source_wallet=sig.source_wallet,
                                condition_id=sig.condition_id,
                            )
                            continue
                        source_size = sig.source_usdc_size
                        if source_size is None or source_size != source_size:
                            self._mark_skipped(sig.source_wallet, "missing_source_size")
                            self._log_event(
                                "warn",
                                "missing source usdcSize for follow_trader_bank_pct mode",
                                condition_id=sig.condition_id,
                            )
                            continue
                        if sig.source_wallet not in source_portfolio_cache:
                            source_portfolio_cache[sig.source_wallet] = await asyncio.to_thread(
                                fetch_positions_value_usd, sig.source_wallet
                            )
                        source_portfolio_usd = source_portfolio_cache[sig.source_wallet]
                        if source_portfolio_usd is None or source_portfolio_usd <= 0:
                            self._mark_skipped(sig.source_wallet, "source_portfolio_unavailable")
                            self._log_event(
                                "warn",
                                "unable to read source portfolio value for follow_trader_bank_pct mode",
                                source_wallet=sig.source_wallet,
                                condition_id=sig.condition_id,
                            )
                            continue
                        source_bank_pct = max(0.0, source_size / source_portfolio_usd)
                        amount_usd = max(min_bet_usd, available_usd * source_bank_pct)
                    if available_usd is not None:
                        amount_usd = min(amount_usd, available_usd)
                    if amount_usd < min_bet_usd and live_allowed:
                        self._mark_skipped(sig.source_wallet, "amount_below_min_after_cap")
                        self._log_event(
                            "warn",
                            "computed amount below min_bet after balance cap, signal skipped",
                            amount_usd=amount_usd,
                            min_bet_usd=min_bet_usd,
                            source_wallet=sig.source_wallet,
                            condition_id=sig.condition_id,
                        )
                        continue

                    try:
                        run_id, decision_id, market_id = await self._prepare_copytrade_records(
                            signal=sig,
                            source_wallet=sig.source_wallet,
                            stake_mode=stake_mode,
                            amount_usd=amount_usd,
                        )
                        cfg_for_bet = dict(cfg_all)
                        cfg_for_bet["betting"] = dict(cfg_all.get("betting") or {})
                        cfg_for_bet["betting"]["execution_enabled"] = bool(live_allowed)
                        if not slippage_protection_enabled:
                            cfg_for_bet["betting"]["slippage_protection_enabled"] = False
                        bet_id = await self._place_copy_bet_via_main_flow(
                            decision_id=decision_id,
                            pipeline_run_id=run_id,
                            market_id=market_id,
                            condition_id=sig.condition_id,
                            side=sig.side,
                            amount_usd=amount_usd,
                            theoretical_price=sig.source_price,
                            config=cfg_for_bet,
                        )
                        if bet_id and live_allowed:
                            self._orders_timestamps.append(time.time())
                        if bet_id:
                            self._mark_copied(sig.source_wallet)
                        self._log_event(
                            "info",
                            "copy bet submitted via main flow",
                            bet_id=bet_id,
                            side=sig.side,
                            source_wallet=sig.source_wallet,
                            condition_id=sig.condition_id,
                            amount_usd=round(amount_usd, 6),
                            stake_mode=stake_mode,
                            live=bool(live_allowed),
                        )
                    except Exception as exc:
                        self._mark_skipped(sig.source_wallet, "submit_failed")
                        self._log_event(
                            "error",
                            "copy bet failed",
                            side=sig.side,
                            source_wallet=sig.source_wallet,
                            condition_id=sig.condition_id,
                            error=str(exc),
                        )

                consecutive_errors = 0
                self._next_check_at_ts = time.time() + poll_seconds
                await asyncio.sleep(poll_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                consecutive_errors += 1
                self._last_error = str(exc)
                self._log_event("error", "copy trading loop error", error=str(exc), errors_in_row=consecutive_errors)
                self._next_check_at_ts = time.time() + 3.0
                await asyncio.sleep(3.0)

    async def get_status(self) -> dict[str, Any]:
        cfg_all = await self._load_cfg()
        c = cfg_all.get("copytrading") or {}
        target_wallets = self._parse_target_wallets(c)
        target_stats_list: list[dict[str, Any]] = []
        for wallet in target_wallets:
            stats = await self._get_target_wallet_stats(
                target_wallet=wallet,
                activity_limit=int(c.get("activity_limit") or 200),
            )
            rt = self._wallet_state(wallet)
            last_buy_at = stats.get("last_buy_at")
            last_buy_age_seconds = None
            parsed_last_buy_ts = _parse_activity_timestamp(last_buy_at)
            if parsed_last_buy_ts is not None:
                last_buy_age_seconds = max(0, int(round(time.time() - parsed_last_buy_ts)))
            next_retry_in_seconds = None
            backoff_until = float(rt.get("backoff_until_ts") or 0.0)
            if backoff_until > time.time():
                next_retry_in_seconds = max(0, int(round(backoff_until - time.time())))
            has_error = bool(rt.get("last_fetch_error")) or bool(stats.get("error")) or next_retry_in_seconds not in (None, 0)
            target_stats_list.append(
                {
                    "wallet": wallet,
                    "open_positions_count": stats.get("open_positions_count"),
                    "recent_activity_count": stats.get("recent_activity_count"),
                    "recent_buy_trades_count": stats.get("recent_buy_trades_count"),
                    "recent_buy_share_pct": stats.get("recent_buy_share_pct"),
                    "open_positions_cash_pnl_sum": stats.get("open_positions_cash_pnl_sum"),
                    "last_buy_at": last_buy_at,
                    "last_buy_age_seconds": last_buy_age_seconds,
                    "updated_at": stats.get("updated_at"),
                    "error": stats.get("error"),
                    "copied_count": int(rt.get("copied_count") or 0),
                    "skipped_count": int(rt.get("skipped_count") or 0),
                    "skip_reasons": rt.get("skip_reasons") or {},
                    "last_fetch_ok_at": rt.get("last_fetch_ok_at"),
                    "last_fetch_error": rt.get("last_fetch_error"),
                    "last_fetch_error_at": rt.get("last_fetch_error_at"),
                    "fetch_error_streak": int(rt.get("fetch_error_streak") or 0),
                    "next_retry_in_seconds": next_retry_in_seconds,
                    "health": "degraded" if has_error else "healthy",
                }
            )
        primary = target_stats_list[0] if target_stats_list else {}
        next_check_at = None
        seconds_until_next_check = None
        if self._next_check_at_ts is not None:
            next_check_at = datetime.fromtimestamp(self._next_check_at_ts, tz=timezone.utc).isoformat()
            seconds_until_next_check = max(0, int(round(self._next_check_at_ts - time.time())))
        return {
            "worker_running": bool(self._task and not self._task.done()),
            "enabled": _as_bool(c.get("enabled"), False),
            "live": _as_bool(c.get("live"), False),
            "binary_only": _as_bool(c.get("binary_only"), True),
            "target_wallet": (target_wallets[0] if target_wallets else None),
            "target_wallets": target_wallets,
            "active_targets_count": len(target_wallets),
            "poll_seconds": c.get("poll_seconds"),
            "activity_limit": c.get("activity_limit"),
            "min_bet_usd": c.get("min_bet_usd"),
            "stake_mode": c.get("stake_mode"),
            "stake_balance_pct": c.get("stake_balance_pct"),
            "stake_trader_ratio": c.get("stake_trader_ratio"),
            "slippage": c.get("slippage"),
            "slippage_protection_enabled": _as_bool(c.get("slippage_protection_enabled"), False),
            "max_orders_per_hour": c.get("max_orders_per_hour"),
            "min_balance_buffer_usd": c.get("min_balance_buffer_usd"),
            "ignore_existing_on_start": _as_bool(c.get("ignore_existing_on_start"), True),
            "orders_last_hour": len(self._orders_timestamps),
            "processed_events_size": len(self._processed_ids),
            "last_loop_at": self._last_loop_at,
            "next_check_at": next_check_at,
            "seconds_until_next_check": seconds_until_next_check,
            "last_error": self._last_error,
            "last_signals_count": self._last_signals_count,
            "target_open_positions_count": primary.get("open_positions_count"),
            "target_recent_activity_count": primary.get("recent_activity_count"),
            "target_recent_buy_trades_count": primary.get("recent_buy_trades_count"),
            "target_recent_buy_share_pct": primary.get("recent_buy_share_pct"),
            "target_open_positions_cash_pnl_sum": primary.get("open_positions_cash_pnl_sum"),
            "target_last_buy_at": primary.get("last_buy_at"),
            "target_last_buy_age_seconds": primary.get("last_buy_age_seconds"),
            "target_stats_updated_at": primary.get("updated_at"),
            "target_stats_error": primary.get("error"),
            "targets": target_stats_list,
            "recent_events": list(self._recent_events)[:120],
        }

    async def _get_target_wallet_stats(self, *, target_wallet: str, activity_limit: int) -> dict[str, Any]:
        if not (target_wallet.startswith("0x") and len(target_wallet) == 42):
            return {
                "open_positions_count": None,
                "recent_activity_count": None,
                "recent_buy_trades_count": None,
                "recent_buy_share_pct": None,
                "open_positions_cash_pnl_sum": None,
                "last_buy_at": None,
                "updated_at": None,
                "error": None,
            }

        now_ts = time.time()
        cache_row = self._target_stats_cache.get(target_wallet) or {}
        cache_at_ts = float(cache_row.get("at_ts") or 0.0)
        cache_data = cache_row.get("data") or {}
        if now_ts - cache_at_ts < 60.0:
            return cache_data

        out: dict[str, Any] = {
            "open_positions_count": None,
            "recent_activity_count": None,
            "recent_buy_trades_count": None,
            "recent_buy_share_pct": None,
            "open_positions_cash_pnl_sum": None,
            "last_buy_at": None,
            "updated_at": _now_iso(),
            "error": None,
        }
        try:
            positions = await self._fetch_open_positions_all(target_wallet)
            out["open_positions_count"] = len(positions)
            out["open_positions_cash_pnl_sum"] = round(
                sum(_safe_float(row.get("cashPnl"), default=0.0) for row in positions if isinstance(row, dict)),
                2,
            )
        except Exception as exc:
            out["error"] = f"positions_error: {exc}"

        try:
            activity = await self._fetch_activity_all(target_wallet)
            out["recent_activity_count"] = len(activity)
            buy_count = sum(
                1
                for row in activity
                if str(row.get("type") or "").upper() == "TRADE" and str(row.get("side") or "").upper() == "BUY"
            )
            out["recent_buy_trades_count"] = buy_count
            if activity:
                out["recent_buy_share_pct"] = round((buy_count / len(activity)) * 100.0, 1)
            last_buy_ts: float | None = None
            last_buy_at: str | None = None
            for row in activity:
                if str(row.get("type") or "").upper() != "TRADE" or str(row.get("side") or "").upper() != "BUY":
                    continue
                ts = _parse_activity_timestamp(row.get("timestamp"))
                if ts is None:
                    continue
                if last_buy_ts is None or ts > last_buy_ts:
                    last_buy_ts = ts
                    last_buy_at = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            out["last_buy_at"] = last_buy_at
        except Exception as exc:
            err = f"activity_error: {exc}"
            out["error"] = f"{out['error']}; {err}" if out.get("error") else err

        self._target_stats_cache[target_wallet] = {"at_ts": now_ts, "data": out}
        return out

    async def _prepare_copytrade_records(
        self,
        *,
        signal: CopySignal,
        source_wallet: str,
        stake_mode: str,
        amount_usd: float,
    ) -> tuple[str, str, str]:
        from app.models.pipeline_run import PipelineRun
        from app.models.market import Market
        from app.models.analysis import Analysis
        from app.models.decision import Decision

        # Keep market_id short and deterministic by condition id.
        market_id = f"copy_{uuid.uuid5(uuid.NAMESPACE_URL, signal.condition_id).hex[:20]}"
        async with async_session_factory() as db:
            m = (await db.execute(select(Market).where(Market.market_id == market_id))).scalar_one_or_none()
            if m is None:
                m = Market(
                    market_id=market_id,
                    condition_id=signal.condition_id,
                    question=signal.title or signal.condition_id,
                    market_slug=None,
                    event_id=None,
                    event_title="Copy trading",
                    tags=["copytrading"],
                    end_date=None,
                )
                db.add(m)
                await db.flush()
            else:
                if not m.condition_id:
                    m.condition_id = signal.condition_id
                if not m.question:
                    m.question = signal.title or signal.condition_id

            run = PipelineRun(
                id=uuid.uuid4(),
                status="running",
                trigger="manual",
                current_stage="copytrading",
                config_snapshot={
                    "copytrading": {
                        "target_wallet": source_wallet,
                        "stake_mode": stake_mode,
                        "signal_condition_id": signal.condition_id,
                        "signal_title": signal.title,
                    }
                },
            )
            db.add(run)
            await db.flush()

            analysis = Analysis(
                id=uuid.uuid4(),
                pipeline_run_id=run.id,
                market_id=market_id,
                research_priority="high",
                structural_reason="copytrading signal",
                p_yes=signal.source_price if signal.side == "yes" else (1 - signal.source_price if signal.source_price is not None else None),
                confidence=0.5,
                reasoning=f"Copied from wallet {source_wallet}",
                p_market=signal.source_price if signal.side == "yes" else (1 - signal.source_price if signal.source_price is not None else None),
                gap=0.0,
            )
            db.add(analysis)
            await db.flush()

            action = "bet_yes" if signal.side == "yes" else "bet_no"
            decision = Decision(
                id=uuid.uuid4(),
                pipeline_run_id=run.id,
                analysis_id=analysis.id,
                market_id=market_id,
                action=action,
                reason=f"copytrading:{source_wallet}",
                kelly_fraction=None,
                bet_size_usd=amount_usd,
                p_yes=analysis.p_yes,
                p_market=analysis.p_market,
                gap=0.0,
                confidence=analysis.confidence,
                bankroll_usd=None,
                decision_trace={
                    "source": "copytrading",
                    "target_wallet": source_wallet,
                    "stake_mode": stake_mode,
                    "signal": {
                        "condition_id": signal.condition_id,
                        "title": signal.title,
                        "source_price": signal.source_price,
                        "source_usdc_size": signal.source_usdc_size,
                    },
                },
            )
            db.add(decision)
            await db.commit()
        return str(run.id), str(decision.id), market_id

    async def _place_copy_bet_via_main_flow(
        self,
        *,
        decision_id: str,
        pipeline_run_id: str,
        market_id: str,
        condition_id: str,
        side: str,
        amount_usd: float,
        theoretical_price: float,
        config: dict[str, Any],
    ) -> str | None:
        from app.services.betting_service import betting_service
        from app.models.pipeline_run import PipelineRun
        from app.models.bet import Bet

        bet_id = await betting_service.place_bet(
            decision_id=decision_id,
            pipeline_run_id=pipeline_run_id,
            market_id=market_id,
            condition_id=condition_id,
            side=side,
            amount_usd=amount_usd,
            theoretical_price=theoretical_price,
            config=config,
            source="copytrading",
        )
        async with async_session_factory() as db:
            run = await db.get(PipelineRun, uuid.UUID(pipeline_run_id))
            if run is not None:
                run.status = "completed"
                run.current_stage = "completed"
                run.finished_at = datetime.now(timezone.utc)
                run.markets_analyzed = 1
                run.decisions_count = 1
                run.bets_placed = 1 if bet_id else 0
                if bet_id:
                    b = await db.get(Bet, uuid.UUID(bet_id))
                    run.error_message = None if b is not None else "bet_not_found_after_submit"
            await db.commit()
        return bet_id


copy_trading_service = CopyTradingService()
