"""Canonical default rows for the `settings` table.

No I/O — used by bootstrap seed and settings reset.
"""
from __future__ import annotations

DEFAULT_SETTINGS: list[tuple[str, str, object, str]] = [
    # (category, key, value, description)

    # --- screener ---
    ("screener", "gamma_api_base", "https://gamma-api.polymarket.com/events", "Gamma API base URL"),
    ("screener", "tag_whitelist", ["economy", "politics", "finance", "us-politics", "world", "elections", "regulation", "law", "global", "health", "science", "technology"], "Tags market must have at least one of (empty = any)"),
    ("screener", "tag_blacklist", ["sports", "soccer", "crypto", "tweets-markets"], "Tags that disqualify a market"),
    ("screener", "min_volume", 5000, "Minimum trading volume in USD"),
    ("screener", "max_volume", None, "Maximum trading volume in USD (null = no limit)"),
    ("screener", "min_hours", 24, "Minimum hours until market closes"),
    ("screener", "max_hours", 168, "Maximum hours until market closes"),
    ("screener", "min_underdog_implied", 0.05, "Minimum implied probability for the underdog side"),
    ("screener", "limit", 5000, "Max events to fetch from Gamma API"),
    ("screener", "request_timeout_sec", 30, "HTTP request timeout in seconds"),
    ("screener", "exclude_open_positions", True, "Skip markets where the configured wallet already has an open position on Polymarket (fetched from Gamma API at screener time)"),

    # --- ranker ---
    ("ranker", "provider", "yandex", "LLM provider: anthropic or yandex"),
    ("ranker", "model", "gpt://b1g7n4milub45em0t8sp/qwen3-235b-a22b-fp8/latest", "Model ID"),
    ("ranker", "temperature", 0.15, "Sampling temperature"),
    ("ranker", "selection_policy", "high_medium", "Stage 1 selection policy: top_n, high_only, or high_medium"),
    ("ranker", "top_n", 5, "Number of top-ranked markets to send to Stage 2"),
    ("ranker", "batch_size", 50, "Max markets per ranker LLM call (0 = no batching)"),

    # --- stage2 ---
    ("stage2", "mode", "full", "Analysis mode: 'full' (news+debate+judge pipeline) or 'simple' (single agent with web search)"),
    ("stage2", "provider", "yandex", "LLM provider: anthropic or yandex"),
    ("stage2", "model", "gpt://b1g7n4milub45em0t8sp/qwen3-235b-a22b-fp8/latest", "Model ID"),
    ("stage2", "temperature", 0.2, "Fallback sampling temperature (used if per-agent temperatures are not set)"),
    ("stage2", "temperature_evidence", 0.1, "Sampling temperature for News and Base Rate agents (low = fewer hallucinations)"),
    ("stage2", "temperature_debate", 0.35, "Sampling temperature for Bull and Bear debate agents (higher = more diverse arguments)"),
    ("stage2", "temperature_judge", 0.05, "Sampling temperature for Judge agent (very low = deterministic JSON output)"),
    ("stage2", "enable_web_search", True, "Enable web search for News and Base Rate agents"),
    ("stage2", "web_search_mode", "gensearch", "Yandex: gensearch or responses"),
    ("stage2", "max_tokens_news", 6000, "Max tokens for News agent"),
    ("stage2", "max_tokens_base_rate", 6000, "Max tokens for Base Rate agent"),
    ("stage2", "max_tokens_debate", 4500, "Max tokens per debate turn"),
    ("stage2", "max_debate_rounds", 3, "Maximum Bull→Bear pairs before judge"),
    ("stage2", "debate_convergence_threshold", 0.08, "Stop debate when |bull_p - bear_p| <= this"),
    ("stage2", "max_tokens_judge", 4000, "Max tokens for Judge"),
    ("stage2", "max_tokens_simple", 8000, "Max tokens for Simple Agent (used when stage2.mode=simple)"),
    ("stage2", "max_parallel_markets", 3, "Max markets analyzed simultaneously (semaphore)"),
    ("stage2", "agent_timeout_sec", 150, "Timeout in seconds for a single LLM call"),
    ("stage2", "market_timeout_sec", 600, "Timeout in seconds for full market analysis"),

    # --- stage3 ---
    ("stage3", "gap_threshold", 0.1, "Minimum |p_yes - p_market| to consider betting"),
    ("stage3", "confidence_threshold", 0.55, "Minimum judge confidence to consider betting"),
    ("stage3", "max_bet_fraction", 0.05, "Maximum fraction of bankroll per bet (Kelly cap and min-order bump ceiling)"),
    ("stage3", "bankroll_usd", 0.0, "Paper bankroll USD: used for Kelly sizing when betting.dry_run_bankroll_source=settings and execution is off"),
    ("stage3", "kelly_divisor", 10.0, "Divide raw Kelly fraction by this (fractional Kelly). Higher = more conservative"),

    # --- scheduler (pipeline only) ---
    ("scheduler", "enabled", False, "Whether scheduled pipeline runs are active"),
    ("scheduler", "run_immediately_on_enable", False, "Run pipeline immediately when auto-run is switched on"),
    ("scheduler", "interval_hours", 6.0, "Run interval in hours (if cron_expression is not set)"),
    ("scheduler", "cron_expression", None, "Cron expression for scheduling (overrides interval_hours)"),
    ("scheduler", "wallet_snapshot_enabled", True, "Whether wallet snapshot scheduler is active"),
    ("scheduler", "wallet_snapshot_interval_minutes", 5.0, "Wallet snapshot interval in minutes"),
    ("scheduler", "settlement_sync_enabled", True, "Whether settlement sync scheduler is active"),
    ("scheduler", "settlement_sync_interval_minutes", 5.0, "Settlement sync interval in minutes"),
    ("scheduler", "order_poll_enabled", True, "Global CLOB open-order poller (fills)"),
    ("scheduler", "order_poll_interval_seconds", 15.0, "Order poll job interval in seconds"),
    ("scheduler", "reconcile_stale_drafts_enabled", True, "Fail stale execution-order drafts and release funds"),
    ("scheduler", "reconcile_interval_seconds", 60.0, "Stale-draft reconciler interval in seconds"),
    ("scheduler", "reconcile_older_than_sec", 60.0, "Drafts older than this (seconds) are considered stale"),

    # --- risk (pre-trade) ---
    ("risk", "execution_kill_switch", False, "When true, no live orders are placed"),
    ("risk", "daily_loss_limit_usd", None, "Stop new risk after this realized loss USD today (UTC); null = off"),
    ("risk", "max_exposure_per_market_usd", None, "Max open exposure per market in USD; null = off"),

    # --- betting ---
    ("betting", "execution_enabled", False, "Safety switch: when False, bets are recorded as dry_run without CLOB orders"),
    (
        "betting",
        "dry_run_bankroll_source",
        "clob",
        "Dry mode only: clob = Kelly sizing from CLOB balance; settings = from stage3.bankroll_usd. Live always uses CLOB.",
    ),
    (
        "betting",
        "order_time_in_force",
        "IOC",
        "CLOB order type: IOC (mapped to FAK in py-clob-client), FAK, FOK, GTC, GTD",
    ),
    ("betting", "taker_fee_bps", 0, "CLOB taker fee in basis points for EV (e.g. 20 = 0.20%)"),
    ("betting", "slippage_protection_enabled", False, "Enable slippage in EV math and CLOB submit guard"),
    (
        "betting",
        "slippage_tolerance",
        0.02,
        "When slippage_protection_enabled: EV slip cost = notional × this fraction; live submit rejects if |best price − theoretical| exceeds this",
    ),
    (
        "betting",
        "allow_min_size_override",
        True,
        "If Kelly-sized stake is below exchange min notional, raise to min only when min ≤ stage3.max_bet_fraction × bankroll and ≤ available bankroll",
    ),

    # --- copytrading ---
    ("copytrading", "enabled", False, "Enable copy-trading worker loop"),
    ("copytrading", "target_wallet", "", "Source wallet to copy (0x...)"),
    ("copytrading", "target_wallets", [], "Source wallets to copy as one combined signal stream"),
    ("copytrading", "min_bet_usd", 1.0, "Fixed USD amount per copied signal"),
    ("copytrading", "stake_mode", "fixed", "Stake mode: fixed | balance_pct | follow_trader_size | follow_trader_bank_pct"),
    ("copytrading", "stake_balance_pct", 0.01, "When stake_mode=balance_pct, use this fraction of available balance"),
    ("copytrading", "stake_trader_ratio", 0.01, "When stake_mode=follow_trader_size, copied stake = source usdcSize × this ratio"),
    ("copytrading", "poll_seconds", 10.0, "Activity polling interval in seconds"),
    ("copytrading", "activity_limit", 200, "How many recent activity rows to fetch each poll"),
    ("copytrading", "live", False, "When true, place real CLOB orders (requires betting.execution_enabled=true and no risk kill-switch)"),
    ("copytrading", "ignore_existing_on_start", True, "On first worker start, mark current activity as processed and copy only new trades"),
    ("copytrading", "binary_only", True, "Copy only explicit YES/NO outcomes; skip non-binary markets"),
    ("copytrading", "max_orders_per_hour", 120, "Safety cap: max copied orders per rolling hour"),
    ("copytrading", "slippage_protection_enabled", False, "When true, enforce slippage guard during live copy order submit"),
    ("copytrading", "slippage", 0.03, "Max allowed |source price - best ask| for copied live order"),
    ("copytrading", "min_balance_buffer_usd", 3.0, "Required free balance reserve above min_bet_usd"),

    # --- llm ---
    ("llm", "anthropic_api_key", "", "Anthropic API key"),
    ("llm", "yandex_llm_api_key", "", "Yandex LLM API key"),
    ("llm", "yandex_llm_folder_id", "", "Yandex folder ID"),
    ("llm", "yandex_llm_endpoint", "https://llm.api.cloud.yandex.net/v1/chat/completions", "Yandex LLM endpoint"),
    ("llm", "yandex_search_api_key", "", "Yandex Search API key"),
    ("llm", "yandex_search_folder_id", "", "Yandex Search folder ID"),
    ("llm", "yandex_llm_auth_mode", "bearer", "Yandex auth mode: bearer or api-key"),
    ("llm", "yandex_search_auth_mode", "api-key", "Yandex Search auth mode"),
    ("llm", "yandex_web_search_mode", "", "Overrides env YANDEX_WEB_SEARCH_MODE (gensearch|responses)"),
    ("llm", "yandex_requests_per_minute", 20, "Rate limit for Yandex LLM API calls per minute"),
    ("llm", "anthropic_requests_per_minute", 50, "Rate limit for Anthropic API calls per minute"),
    ("llm", "max_retries_429", 5, "Max retry attempts for 429 Too Many Requests errors"),
    ("llm", "max_retries_5xx", 3, "Max retry attempts for 5xx server errors"),
]
