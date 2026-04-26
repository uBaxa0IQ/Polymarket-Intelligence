/**
 * Extended UI copy for Settings. Server `description` stays the short source of truth;
 * this file adds context, units, and cross-links without requiring a backend deploy.
 */
export type SettingHelpRelated = { category: string; key: string; note?: string }

export type SettingHelpDoc = {
  /** Optional heading inside the panel (defaults to the raw key). */
  title?: string
  /** Main explanation — one string or paragraphs. */
  details: string | string[]
  related?: SettingHelpRelated[]
  warning?: string
}

const H: Record<string, SettingHelpDoc> = {
  // --- screener ---
  'screener:gamma_api_base': {
    title: 'Gamma API base URL',
    details:
      'Base URL for Polymarket’s Gamma HTTP API used when fetching events/markets for screening. Change only if you run a compatible proxy or Polymarket publishes a new endpoint.',
  },
  'screener:tag_whitelist': {
    title: 'Tag whitelist',
    details:
      'Markets must include at least one of these Gamma tag slugs to pass the screener. Use an empty list in the JSON value to allow any tag (not recommended — noisy).',
    related: [{ category: 'screener', key: 'tag_blacklist', note: 'Hard excludes still apply' }],
  },
  'screener:tag_blacklist': {
    title: 'Tag blacklist',
    details:
      'If a market has any of these tags, it is dropped regardless of whitelist. Use to filter domains you never want in the pipeline (e.g. sports, low-signal social markets).',
    related: [{ category: 'screener', key: 'tag_whitelist' }],
  },
  'screener:min_volume': {
    title: 'Minimum volume',
    details: 'Minimum 24h (or API-reported) trading volume in USD for a market to be considered. Higher = fewer, more liquid ideas.',
  },
  'screener:max_volume': {
    title: 'Maximum volume',
    details:
      'Upper cap on volume in USD; markets above this are excluded. Use null / omit limit for no maximum — useful to skip only ultra-thin markets without capping the top.',
  },
  'screener:min_hours': {
    title: 'Minimum hours to close',
    details: 'Markets resolving sooner than this many hours are skipped — avoids churn right at resolution.',
  },
  'screener:max_hours': {
    title: 'Maximum hours to close',
    details: 'Markets resolving later than this horizon are skipped — keeps the universe in a window where research and execution still matter.',
  },
  'screener:min_underdog_implied': {
    title: 'Minimum underdog implied',
    details:
      'Minimum implied probability for the “underdog” side (the less likely outcome by price). Filters out totally one-sided markets where edge is structurally small.',
  },
  'screener:limit': {
    title: 'Gamma fetch limit',
    details: 'Maximum number of events to pull from Gamma per screener run. Trade-off: coverage vs API load and runtime.',
  },
  'screener:request_timeout_sec': {
    title: 'HTTP timeout',
    details: 'Per-request timeout in seconds for outbound HTTP calls during screening.',
  },

  // --- ranker ---
  'ranker:provider': {
    title: 'Ranker LLM provider',
    details: 'Which vendor serves Stage 1 (triage/ranking). Must match configured API keys and rate limits in the llm category.',
    related: [
      { category: 'ranker', key: 'model' },
      { category: 'llm', key: 'anthropic_api_key', note: 'Secrets' },
      { category: 'llm', key: 'yandex_llm_api_key', note: 'Secrets' },
    ],
  },
  'ranker:model': {
    title: 'Ranker model',
    details: 'Model identifier as required by the provider (e.g. Claude id or Yandex Foundation Models URI). Wrong model strings fail at runtime.',
  },
  'ranker:temperature': {
    title: 'Ranker temperature',
    details: 'Sampling temperature for Stage 1. Lower = more deterministic ranking; higher = more variation run-to-run.',
  },
  'ranker:selection_policy': {
    title: 'Selection policy',
    details: [
      'Controls how triage labels (high / medium / low research priority) map to markets forwarded to Stage 2.',
      'top_n: take up to top_n markets in priority order.',
      'high_only: only “high” priority.',
      'high_medium: “high” and “medium”.',
    ],
    related: [{ category: 'ranker', key: 'top_n' }],
  },
  'ranker:top_n': {
    title: 'Top N markets',
    details: 'After ranking/triage, at most this many markets continue to Stage 2 when policy is top_n (subject to how many pass filters).',
    related: [{ category: 'ranker', key: 'selection_policy' }],
  },

  // --- stage2 ---
  'stage2:provider': {
    title: 'Stage 2 provider',
    details: 'LLM vendor for News, Base Rate, debate, and Judge agents. Independent from ranker provider if you want to split traffic.',
    related: [{ category: 'stage2', key: 'model' }],
  },
  'stage2:mode': {
    title: 'Analysis mode',
    details: [
      "full — multi-agent pipeline: news, base rate, bull/bear debate, then judge.",
      'simple — one agent with web search; faster and cheaper, no debate/judge stages.',
    ],
    related: [{ category: 'stage2', key: 'max_tokens_simple', note: 'Token cap in simple mode' }],
  },
  'stage2:model': {
    title: 'Stage 2 model',
    details: 'Model id for all Stage 2 agents unless overridden in code paths. Large context models help for long evidence + debate transcripts.',
  },
  'stage2:temperature': {
    title: 'Stage 2 temperature',
    details: 'Default sampling temperature for Stage 2 calls. Debate/judge prompts still expect coherent JSON on the last line.',
  },
  'stage2:enable_web_search': {
    title: 'Web search',
    details: 'When enabled, News and Base Rate agents can call configured search APIs (Yandex). Adds latency and cost but improves recency.',
    related: [{ category: 'stage2', key: 'web_search_mode' }],
  },
  'stage2:web_search_mode': {
    title: 'Yandex web search mode',
    details: 'Vendor-specific mode string (e.g. gensearch vs responses). Must match what your Yandex project supports.',
  },
  'stage2:max_tokens_news': {
    title: 'News agent max tokens',
    details: 'Completion token budget for the News agent response.',
  },
  'stage2:max_tokens_base_rate': {
    title: 'Base rate agent max tokens',
    details: 'Completion token budget for the Base Rate agent response.',
  },
  'stage2:max_tokens_debate': {
    title: 'Debate max tokens',
    details: 'Per-turn token cap for Bull/Bear debate messages (prose + trailing JSON line).',
  },
  'stage2:max_debate_rounds': {
    title: 'Max debate rounds',
    details: 'Maximum Bull→Bear pairs before the judge runs. Higher = deeper argument, more tokens and time.',
    related: [{ category: 'stage2', key: 'debate_convergence_threshold' }],
  },
  'stage2:debate_convergence_threshold': {
    title: 'Debate convergence',
    details:
      'Early stop when |p_yes bull estimate − p_yes bear estimate| is at or below this threshold. Set smaller to force more rounds, larger to stop sooner.',
  },
  'stage2:max_tokens_judge': {
    title: 'Judge max tokens',
    details: 'Token budget for the final judge JSON (p_yes, confidence, reasoning).',
  },
  'stage2:max_parallel_markets': {
    title: 'Parallel markets',
    details: 'Concurrency limit for Stage 2 across markets (semaphore). Higher speeds up batches but increases parallel LLM load and rate-limit risk.',
  },
  'stage2:agent_timeout_sec': {
    title: 'Per-agent timeout',
    details: 'Wall-clock timeout for a single LLM invocation within Stage 2. Prevents one hung call from blocking the worker forever.',
  },
  'stage2:market_timeout_sec': {
    title: 'Per-market timeout',
    details: 'Total time budget for full analysis of one market (all agents + debate + judge).',
  },

  // --- stage3 ---
  'stage3:gap_threshold': {
    title: 'Gap threshold',
    details:
      'Minimum absolute gap between model p_yes and market-implied probability before the system considers a bet. Larger = fewer but more “disagreement” trades.',
    related: [{ category: 'stage3', key: 'confidence_threshold' }],
  },
  'stage3:confidence_threshold': {
    title: 'Confidence threshold',
    details: 'Judge confidence must be at least this value to allow sizing a bet. Filters low-conviction edges.',
    related: [{ category: 'stage3', key: 'gap_threshold' }],
  },
  'stage3:max_bet_fraction': {
    title: 'Max bet fraction',
    details:
      'Hard cap on Kelly stake as a fraction of effective bankroll, and ceiling used when lifting size to the exchange minimum. Primary per-bet size knob together with Kelly divisor.',
    related: [{ category: 'stage3', key: 'kelly_divisor' }],
  },
  'stage3:bankroll_usd': {
    title: 'Paper bankroll (USD)',
    details:
      'Used for Kelly / notional sizing when execution is off or when dry_run_bankroll_source is set to settings — not your live CLOB balance.',
    related: [{ category: 'betting', key: 'dry_run_bankroll_source' }],
  },
  'stage3:kelly_divisor': {
    title: 'Kelly divisor',
    details: [
      'Fractional Kelly: raw Kelly stake is divided by this number. Larger divisor = smaller positions.',
      'Below a fixed internal confidence threshold (not configurable), the Kelly fraction is additionally halved in code.',
    ],
    warning: 'Mis-set divisors near zero can explode sizing; keep in a sane range (e.g. ≥ 2).',
  },

  // --- scheduler ---
  'scheduler:enabled': {
    title: 'Scheduled pipeline',
    details: 'Master switch for automatic pipeline runs on the interval or cron configured below.',
    related: [{ category: 'scheduler', key: 'interval_hours' }, { category: 'scheduler', key: 'cron_expression' }],
  },
  'scheduler:run_immediately_on_enable': {
    title: 'Run immediately on enable',
    details: 'When turning scheduled runs on, optionally trigger one pipeline run right away instead of waiting for the next tick.',
  },
  'scheduler:interval_hours': {
    title: 'Run interval (hours)',
    details: 'Hours between pipeline runs when no cron_expression is set.',
    related: [{ category: 'scheduler', key: 'cron_expression', note: 'Cron overrides interval' }],
  },
  'scheduler:cron_expression': {
    title: 'Cron expression',
    details: 'If set, takes precedence over interval_hours for pipeline timing. Use standard 5-field cron as supported by your deployment.',
  },
  'scheduler:wallet_snapshot_enabled': {
    title: 'Wallet snapshot scheduler',
    details: 'Periodically records wallet / balance snapshots for dashboards and risk views.',
  },
  'scheduler:wallet_snapshot_interval_minutes': {
    title: 'Wallet snapshot interval',
    details: 'Minutes between wallet snapshot jobs.',
  },
  'scheduler:settlement_sync_enabled': {
    title: 'Settlement sync',
    details: 'Background job to reconcile bet outcomes with exchange settlement data.',
  },
  'scheduler:settlement_sync_interval_minutes': {
    title: 'Settlement sync interval',
    details: 'Minutes between settlement sync passes.',
  },
  'scheduler:order_poll_enabled': {
    title: 'Order poll',
    details: 'Global poller for open CLOB orders (fills, partial fills). Needed for accurate live state when trading.',
  },
  'scheduler:order_poll_interval_seconds': {
    title: 'Order poll interval',
    details: 'Seconds between order poll cycles. Lower = fresher state, more API traffic.',
  },
  'scheduler:reconcile_stale_drafts_enabled': {
    title: 'Stale draft reconciler',
    details: 'Fails old execution-order drafts that never completed so funds/locks are released consistently.',
  },
  'scheduler:reconcile_interval_seconds': {
    title: 'Reconciler interval',
    details: 'How often the stale-draft reconciler runs.',
  },
  'scheduler:reconcile_older_than_sec': {
    title: 'Stale draft age',
    details: 'Drafts older than this many seconds are candidates for automatic failure/cleanup.',
  },

  // --- risk ---
  'risk:execution_kill_switch': {
    title: 'Execution kill switch',
    details: 'When true, the system must not place new live orders regardless of other toggles. Use for emergencies.',
    warning: 'Pair with betting.execution_enabled off for defense in depth.',
    related: [{ category: 'betting', key: 'execution_enabled' }],
  },
  'risk:daily_loss_limit_usd': {
    title: 'Daily loss limit',
    details:
      'If set, new risk-taking stops after realized loss today (UTC) exceeds this USD amount. null disables the limit.',
  },
  'risk:max_exposure_per_market_usd': {
    title: 'Max exposure per market',
    details: 'Cap on open exposure (USD) for a single market; null disables. Reduces tail risk from one outcome.',
  },

  // --- betting ---
  'betting:execution_enabled': {
    title: 'Live execution',
    details:
      'When false, the system records intended bets as dry_run and does not send CLOB orders. Always start false until keys, geolocation, and risk limits are verified.',
    related: [
      { category: 'risk', key: 'execution_kill_switch' },
      { category: 'betting', key: 'dry_run_bankroll_source' },
    ],
  },
  'betting:dry_run_bankroll_source': {
    title: 'Dry-run bankroll source',
    details: [
      'clob: size paper trades from live CLOB account balance (read-only balance path).',
      'settings: size from stage3.bankroll_usd for repeatable paper tests.',
      'Live trading always uses real CLOB balances regardless of this key.',
    ],
    related: [{ category: 'stage3', key: 'bankroll_usd' }],
  },
  'betting:order_time_in_force': {
    title: 'Order time-in-force',
    details: [
      'IOC: in py-clob-client this maps to FAK (fill-and-kill: take liquidity, cancel any unfilled remainder).',
      'FAK: same as IOC mapping when using the Polymarket Python client.',
      'FOK: entire size must fill at once or cancel.',
      'GTC: rest on book until filled or canceled.',
      'GTD: good-til-date (requires expiration in the client; rarely used here).',
    ],
  },
  'betting:taker_fee_bps': {
    title: 'Taker fee (basis points)',
    details: 'Fee in bps (1 bp = 0.01%) applied in EV / sizing math for taker-style fills. Match your exchange tier.',
  },
  'betting:slippage_protection_enabled': {
    title: 'Enable slippage protection',
    details:
      'When enabled, Stage 3 EV subtracts slippage cost (notional × slippage_tolerance) and live Stage 4 submit uses the same tolerance as max |market price − theoretical|.',
    related: [{ category: 'betting', key: 'slippage_tolerance' }],
  },
  'betting:slippage_tolerance': {
    title: 'Slippage tolerance',
    details:
      'Single fraction (e.g. 0.02): used as slippage cost in EV math (× notional) and as the absolute price-move guard on CLOB submit. Only applies when slippage_protection_enabled is true.',
    related: [{ category: 'betting', key: 'slippage_protection_enabled' }],
  },
  'betting:allow_min_size_override': {
    title: 'Min size override',
    details:
      'When Kelly-sized stake is below the exchange minimum, allow bumping up to that minimum only if it still fits under stage3.max_bet_fraction × bankroll and available balance.',
    related: [{ category: 'stage3', key: 'max_bet_fraction' }],
  },

  // --- copytrading ---
  'copytrading:enabled': {
    title: 'Enable copy trading worker',
    details: 'Master switch for the background copy-trading loop. When false, worker stays idle and no signals are processed.',
  },
  'copytrading:target_wallet': {
    title: 'Target wallet',
    details: 'Source wallet (0x...) whose BUY trade activity is mirrored into copy signals.',
  },
  'copytrading:target_wallets': {
    title: 'Target wallets',
    details:
      'JSON array of source wallets combined into one signal stream. Example: ["0xabc...", "0xdef..."]. If empty, legacy target_wallet is used.',
    related: [{ category: 'copytrading', key: 'target_wallet' }],
  },
  'copytrading:min_bet_usd': {
    title: 'Min bet USD',
    details: 'Base minimum copied stake. In fixed mode this is the exact order size; in dynamic modes this acts as a floor.',
  },
  'copytrading:stake_mode': {
    title: 'Stake mode',
    details: [
      'fixed: always use min_bet_usd.',
      'balance_pct: use available balance × stake_balance_pct, but not below min_bet_usd.',
      'follow_trader_size: use source trade usdcSize × stake_trader_ratio, but not below min_bet_usd.',
      'follow_trader_bank_pct: compute source trade fraction = usdcSize / source portfolio value, then apply same fraction to your available balance.',
    ],
  },
  'copytrading:stake_balance_pct': {
    title: 'Balance percent stake',
    details: 'Used only when stake_mode=balance_pct. Example: 0.01 means 1% of available balance per copied signal.',
  },
  'copytrading:stake_trader_ratio': {
    title: 'Trader size ratio',
    details: 'Used only when stake_mode=follow_trader_size. Copied amount = source usdcSize × ratio.',
  },
  'copytrading:poll_seconds': {
    title: 'Poll interval',
    details: 'How often activity is fetched from Data API. Lower values react faster but increase request volume.',
  },
  'copytrading:live': {
    title: 'Live mode',
    details: 'When enabled, worker attempts real CLOB orders. Requires betting.execution_enabled=true and risk.execution_kill_switch=false.',
    warning: 'Keep this off until you verify wallet, limits, and dry-run behavior.',
  },
  'copytrading:binary_only': {
    title: 'Binary markets only',
    details: 'Safety mode: copy only explicit YES/NO outcomes and skip unsupported non-binary events.',
  },
  'copytrading:ignore_existing_on_start': {
    title: 'Ignore existing on start',
    details: 'On first worker start, current activity is marked as processed and only newly appearing trades are copied.',
  },
  'copytrading:max_orders_per_hour': {
    title: 'Hourly order cap',
    details: 'Safety limit for copied orders in a rolling 1-hour window.',
  },
  'copytrading:slippage_protection_enabled': {
    title: 'Slippage protection',
    details: 'When enabled, live copy orders enforce the slippage guard. When disabled, slippage checks are skipped.',
    warning: 'Default is disabled. Enable only if you want strict source-price guardrails.',
  },
  'copytrading:slippage': {
    title: 'Slippage guard',
    details: 'Maximum allowed absolute difference between source price and current best ask before rejecting a live copy order.',
  },
  'copytrading:min_balance_buffer_usd': {
    title: 'Balance reserve',
    details: 'Required free collateral reserve above min_bet_usd before a live copied order is allowed.',
  },

  // --- llm ---
  'llm:anthropic_api_key': {
    title: 'Anthropic API key',
    details: 'API key for Claude models when ranker/stage2 provider is anthropic. Stored in DB — restrict database access.',
    warning: 'Never commit keys to git; rotate if leaked.',
  },
  'llm:yandex_llm_api_key': {
    title: 'Yandex LLM API key',
    details: 'API key for Yandex Foundation Models chat/completions.',
  },
  'llm:yandex_llm_folder_id': {
    title: 'Yandex LLM folder ID',
    details: 'Yandex Cloud folder id that owns the LLM endpoint and billing.',
  },
  'llm:yandex_llm_endpoint': {
    title: 'Yandex LLM endpoint',
    details: 'HTTP base for chat completions. Change if Yandex documents a new regional endpoint.',
  },
  'llm:yandex_search_api_key': {
    title: 'Yandex Search API key',
    details: 'Key for web search used in Stage 2 when web search is enabled.',
  },
  'llm:yandex_search_folder_id': {
    title: 'Yandex Search folder ID',
    details: 'Folder id for Search API billing/quota.',
  },
  'llm:yandex_llm_auth_mode': {
    title: 'Yandex LLM auth mode',
    details: 'How requests authenticate (e.g. bearer IAM token vs static api-key) — must match how you deploy credentials.',
  },
  'llm:yandex_search_auth_mode': {
    title: 'Yandex Search auth mode',
    details: 'Same idea for the Search API client.',
  },
  'llm:yandex_web_search_mode': {
    title: 'Yandex web search mode override',
    details: 'Optional override for env YANDEX_WEB_SEARCH_MODE (e.g. gensearch | responses). Empty means use environment default.',
    related: [{ category: 'stage2', key: 'web_search_mode' }],
  },
  'llm:yandex_requests_per_minute': {
    title: 'Yandex LLM rate limit',
    details: 'Client-side throttle: max LLM calls per minute to reduce 429s.',
  },
  'llm:anthropic_requests_per_minute': {
    title: 'Anthropic rate limit',
    details: 'Client-side throttle for Anthropic API calls per minute.',
  },
  'llm:max_retries_429': {
    title: '429 retries',
    details: 'Maximum backoff retries when the provider returns HTTP 429 Too Many Requests.',
  },
  'llm:max_retries_5xx': {
    title: '5xx retries',
    details: 'Maximum retries for transient server errors (5xx).',
  },
}

export function settingHelpKey(category: string, key: string): string {
  return `${category}:${key}`
}

export function getSettingHelp(category: string, key: string): SettingHelpDoc | undefined {
  return H[settingHelpKey(category, key)]
}
