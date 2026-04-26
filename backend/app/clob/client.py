"""Polymarket CLOB client wrapper using py-clob-client."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _fee_from_notional(size: float, price: float, fee_rate_bps: float) -> float:
    """Compute fee in USD from fill notional and bps."""
    if size <= 0 or price <= 0 or fee_rate_bps <= 0:
        return 0.0
    return round(size * price * fee_rate_bps / 10000.0, 6)


def _extract_best_ask(order_book: object) -> float:
    """Extract best ask price across py-clob-client payload variants.

    Some client versions return a dict-like object ({"asks": [...]});
    others return typed objects (e.g. OrderBookSummary with .asks).
    """
    if isinstance(order_book, dict):
        asks = order_book.get("asks") or []
    else:
        asks = getattr(order_book, "asks", None) or []

    if not asks:
        raise ValueError("No asks in orderbook")

    top = asks[0]
    if isinstance(top, dict):
        price = top.get("price")
    else:
        price = getattr(top, "price", None)

    if price is None:
        raise ValueError("Best ask has no price field")

    return float(price)


class PolymarketCLOB:
    """Thin wrapper around py-clob-client for placing market orders."""

    def __init__(
        self,
        private_key: str,
        api_key: str,
        api_secret: str,
        api_passphrase: str,
        chain_id: int = 137,
        funder: str | None = None,
        signature_type: int | None = None,
    ):
        try:
            from py_clob_client.client import ClobClient
            from py_clob_client.clob_types import ApiCreds
            self._funder = (funder or "").strip() or None
            self._signature_type = signature_type if signature_type is not None else (1 if self._funder else 0)
            self._client = ClobClient(
                host="https://clob.polymarket.com",
                key=private_key,
                chain_id=chain_id,
                creds=ApiCreds(
                    api_key=api_key,
                    api_secret=api_secret,
                    api_passphrase=api_passphrase,
                ),
                funder=self._funder,
                signature_type=self._signature_type,
            )
        except ImportError:
            raise ImportError("py-clob-client is not installed. Run: pip install py-clob-client")

    def get_token_id(self, condition_id: str, side: str) -> str:
        """Resolve condition_id + side to a token_id."""
        market = self._client.get_market(condition_id)
        tokens = market.get("tokens", [])
        target_outcome = "Yes" if side == "yes" else "No"
        for token in tokens:
            if token.get("outcome") == target_outcome:
                return token["token_id"]
        raise ValueError(f"Could not find {target_outcome} token for condition_id={condition_id}")

    def place_market_order(
        self,
        condition_id: str,
        side: str,
        amount_usd: float,
        theoretical_price: float,
        slippage_protection: float | None = None,
        time_in_force: str = "IOC",
    ) -> dict:
        """Buy outcome tokens for up to ``amount_usd`` at/through the current best ask.

        Uses ``create_market_order`` (USDC notional) so amounts match the CLOB
        precision rules (maker 2 / taker 5 decimals for market buys). Do not use
        raw ``size=amount/price`` + ``create_order`` — that path can hit 400
        "invalid amounts" from the API.

        Returns {"order_id": str, "price": float}
        """
        from py_clob_client.clob_types import MarketOrderArgs, OrderType

        tif = str(time_in_force or "IOC").strip().upper()
        # py-clob-client 0.18+: OrderType has GTC, FOK, GTD, FAK — no IOC. IOC maps to FAK
        # (fill-and-kill: fill what you can, cancel remainder — same intent as market-style IOC).
        order_type_by_tif = {
            "GTC": OrderType.GTC,
            "IOC": OrderType.FAK,
            "FAK": OrderType.FAK,
            "FOK": OrderType.FOK,
            "GTD": OrderType.GTD,
        }
        order_type = order_type_by_tif.get(tif)
        if order_type is None:
            raise ValueError(
                f"Unsupported time_in_force '{time_in_force}', expected one of: GTC, IOC, FAK, FOK, GTD"
            )

        token_id = self.get_token_id(condition_id, side)

        # Get order book (supports both dict and typed SDK responses).
        book = self._client.get_order_book(token_id)
        try:
            best_ask = _extract_best_ask(book)
        except ValueError as exc:
            raise ValueError(f"{exc} for token_id={token_id}") from exc

        # Slippage protection (optional; None/<=0 disables the guard).
        if slippage_protection is not None and slippage_protection > 0 and abs(best_ask - theoretical_price) > slippage_protection:
            raise ValueError(
                f"Slippage too large: best_ask={best_ask:.4f}, theoretical={theoretical_price:.4f}, "
                f"diff={abs(best_ask - theoretical_price):.4f} > {slippage_protection}"
            )

        # USDC notional: API allows 2 decimal places for market-buy maker side; float noise
        # (e.g. 2.4200000001) can still slip through to signing — normalize first.
        amount_usdc_2 = round(float(amount_usd), 2)
        if amount_usdc_2 <= 0:
            raise ValueError("amount_usd must be positive after rounding to cents")

        # Market BUY: pass USDC notional; SDK applies tick-based rounding (avoids 400 invalid amounts).
        margs = MarketOrderArgs(
            token_id=token_id,
            amount=amount_usdc_2,
            side="BUY",
            price=best_ask,
            order_type=order_type,
        )
        signed_order = self._client.create_market_order(margs)
        resp = self._client.post_order(signed_order, order_type)

        return {
            "order_id": resp.get("orderID") or resp.get("id"),
            "price": best_ask,
        }

    def cancel_order(self, order_id: str) -> bool:
        """Try to cancel a live order by ID."""
        try:
            # py-clob-client method names differ by version, so try known variants.
            if hasattr(self._client, "cancel"):
                self._client.cancel(order_id)
                return True
            if hasattr(self._client, "cancel_order"):
                self._client.cancel_order(order_id)
                return True
            if hasattr(self._client, "cancel_orders"):
                self._client.cancel_orders([order_id])
                return True
        except Exception as exc:
            logger.warning("cancel_order failed for %s: %s", order_id, exc)
            return False
        logger.warning("cancel_order unsupported by py-clob-client version for %s", order_id)
        return False

    def get_address(self) -> str | None:
        # For proxy accounts (email/social wallet), funder is the effective
        # account address used for balances/positions.
        if self._funder:
            return self._funder
        try:
            return self._client.get_address()
        except Exception:
            return None

    def get_collateral_balance_allowance(self) -> dict | None:
        """CLOB collateral (USDC) balance + allowance; shape from Polymarket API."""
        try:
            from py_clob_client.clob_types import AssetType, BalanceAllowanceParams

            params = BalanceAllowanceParams(
                asset_type=AssetType.COLLATERAL,
            )
            return self._client.get_balance_allowance(params)
        except Exception as exc:
            logger.warning("get_balance_allowance failed: %s", exc)
            return None

    def get_order(self, order_id: str) -> dict | None:
        try:
            return self._client.get_order(order_id)
        except Exception as exc:
            logger.warning("get_order failed for %s: %s", order_id, exc)
            return None

    def get_order_fills(self, order_id: str) -> dict | None:
        """Return fill details for an order: size_matched, price, fee_rate_bps.

        Tries the CLOB trades endpoint first; falls back to get_order() fields.
        """
        try:
            from py_clob_client.clob_types import TradeParams
            params = TradeParams(id=order_id)
            trades = self._client.get_trades(params)
            if trades:
                total_size = 0.0
                weighted_notional = 0.0
                total_fee = 0.0
                for t in trades:
                    size = float(t.get("size", 0) or 0)
                    if size <= 0:
                        continue
                    price = float(t.get("price", 0) or 0)
                    fee_rate_bps = float(t.get("fee_rate_bps", 0) or 0)

                    total_size += size
                    if price > 0:
                        weighted_notional += size * price

                    # Prefer explicit fee from API when available; else compute from notional.
                    explicit_fee = t.get("fee")
                    if explicit_fee is not None:
                        try:
                            total_fee += float(explicit_fee)
                            continue
                        except (TypeError, ValueError):
                            pass
                    total_fee += _fee_from_notional(size, price, fee_rate_bps)

                avg_price = (weighted_notional / total_size) if total_size > 0 else None
                return {
                    "size_matched": total_size,
                    "avg_price": avg_price,
                    "fee_usd": round(total_fee, 6),
                    "status": "filled" if total_size > 0 else "open",
                }
        except Exception:
            pass

        order = self.get_order(order_id)
        if not order:
            return None
        size_matched = float(order.get("size_matched") or order.get("sizeMatched") or 0)
        fee_rate_bps = float(order.get("fee_rate_bps") or order.get("feeRateBps") or 0)
        price = float(order.get("price") or 0)
        status_raw = str(order.get("status") or "").upper()
        status = "filled" if status_raw in ("FILLED", "MATCHED") else ("cancelled" if status_raw in ("CANCELLED", "CANCELED") else "open")
        explicit_fee = order.get("fee") or order.get("feePaid") or order.get("fee_paid")
        if explicit_fee is not None:
            try:
                fee_usd = round(float(explicit_fee), 6)
            except (TypeError, ValueError):
                fee_usd = _fee_from_notional(size_matched, price, fee_rate_bps)
        else:
            fee_usd = _fee_from_notional(size_matched, price, fee_rate_bps)
        return {
            "size_matched": size_matched,
            "avg_price": price if price > 0 else None,
            "fee_usd": fee_usd,
            "status": status,
            "raw_status": status_raw,
        }

    def get_market_constraints(self, condition_id: str) -> dict:
        """Return market trading constraints: tick_size and min_order_size (shares)."""
        try:
            market = self._client.get_market(condition_id)
        except Exception as exc:
            logger.warning("get_market failed for %s: %s", condition_id, exc)
            return {"tick_size": None, "min_order_size": None}

        def _to_float(v):
            try:
                if v is None:
                    return None
                return float(v)
            except (TypeError, ValueError):
                return None

        # Different API payload versions may use different keys.
        tick_size = (
            _to_float(market.get("tick_size"))
            or _to_float(market.get("tickSize"))
            or _to_float(market.get("minimum_tick_size"))
            or _to_float(market.get("min_tick_size"))
        )
        min_order_size = (
            _to_float(market.get("min_order_size"))
            or _to_float(market.get("minimum_order_size"))
            or _to_float(market.get("minSize"))
        )

        return {"tick_size": tick_size, "min_order_size": min_order_size}


def get_clob_client(config: dict) -> PolymarketCLOB | None:
    """Build a CLOB client from config (settings table) or env vars."""
    import os

    private_key = os.getenv("POLYMARKET_PRIVATE_KEY", "")
    api_key = os.getenv("POLYMARKET_API_KEY", "")
    api_secret = os.getenv("POLYMARKET_API_SECRET", "")
    api_passphrase = os.getenv("POLYMARKET_API_PASSPHRASE", "")
    proxy_address = (os.getenv("POLYMARKET_PROXY_ADDRESS", "") or "").strip() or None
    signature_type_env = (os.getenv("POLYMARKET_SIGNATURE_TYPE", "") or "").strip()
    try:
        signature_type = int(signature_type_env) if signature_type_env else (1 if proxy_address else 0)
    except ValueError:
        logger.warning(
            "Invalid POLYMARKET_SIGNATURE_TYPE=%r, falling back to %d",
            signature_type_env,
            1 if proxy_address else 0,
        )
        signature_type = 1 if proxy_address else 0

    if not all([private_key, api_key, api_secret, api_passphrase]):
        logger.warning("Polymarket CLOB credentials not configured")
        return None

    try:
        return PolymarketCLOB(
            private_key=private_key,
            api_key=api_key,
            api_secret=api_secret,
            api_passphrase=api_passphrase,
            funder=proxy_address,
            signature_type=signature_type,
        )
    except ImportError:
        logger.warning("py-clob-client is not installed; live CLOB is unavailable (pip install py-clob-client)")
        return None
