const BASE = '/api/v1'

export function getToken(): string | null {
  return localStorage.getItem('access_token')
}

export function setToken(token: string): void {
  localStorage.setItem('access_token', token)
}

export function clearToken(): void {
  localStorage.removeItem('access_token')
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getToken()
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  })

  if (res.status === 401) {
    clearToken()
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status} ${text}`)
  }

  if (res.status === 204) return undefined as T
  return res.json()
}

// Auth
export const login = (username: string, password: string) =>
  request<{ access_token: string; token_type: string }>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })

// Dashboard
export const fetchSummary = () => request<any>('/dashboard/summary')
export const fetchPnlChart = (period?: string) =>
  request<any[]>(
    `/dashboard/pnl-chart${period ? `?period=${encodeURIComponent(period)}&exclude_dry_run=true` : '?exclude_dry_run=true'}`,
  )
export const fetchRecentActivity = () => request<any[]>('/dashboard/recent-activity')

// Pipeline
export type PipelineRun = {
  id: string
  started_at: string | null
  finished_at: string | null
  status: string
  trigger: string
  current_stage: string | null
  config_snapshot: Record<string, unknown> | null
  markets_screened: number
  markets_ranked: number
  markets_analyzed: number
  decisions_count: number
  bets_placed: number
  error_message: string | null
}

export type PipelineRunAccepted = { run_id: string }

export const fetchRuns = (params?: string) =>
  request<PipelineRun[]>(`/pipeline/runs${params ? '?' + params : ''}`)
export const fetchRun = (id: string) => request<PipelineRun>(`/pipeline/runs/${id}`)
export const fetchActiveRun = () => request<PipelineRun | null>('/pipeline/runs/active')
export const fetchRunLLMCalls = (id: string) => request<any[]>(`/pipeline/runs/${id}/llm-calls`)
export const fetchRunAnalyses = (id: string) => request<any[]>(`/pipeline/runs/${id}/analyses`)
export const fetchRunScreener = (id: string) => request<any>(`/pipeline/runs/${id}/screener`)
export const fetchRunRanker = (id: string) => request<any>(`/pipeline/runs/${id}/ranker`)
export type RunTraceQuery = {
  events_limit?: number
  events_offset?: number
  severity?: string
  stage?: string
}

export type RunTraceExecutionEvent = {
  id: number
  decision_id?: string | null
  bet_id?: string | null
  event_time: string | null
  stage: string
  event_type: string
  severity: string
  client_order_id?: string | null
  exchange_order_id?: string | null
  payload?: Record<string, unknown>
}

export type RunTraceResponse = {
  decisions: any[]
  execution_events: RunTraceExecutionEvent[]
  execution_events_total: number
  execution_events_limit: number
  execution_events_offset: number
}

export const fetchRunTrace = (id: string, q?: RunTraceQuery) => {
  const p = new URLSearchParams()
  if (q?.events_limit != null) p.set('events_limit', String(q.events_limit))
  if (q?.events_offset != null) p.set('events_offset', String(q.events_offset))
  if (q?.severity) p.set('severity', q.severity)
  if (q?.stage) p.set('stage', q.stage)
  const qs = p.toString()
  return request<RunTraceResponse>(`/pipeline/runs/${id}/trace${qs ? `?${qs}` : ''}`)
}
export const fetchRunMarketDetail = (runId: string, marketId: string) =>
  request<any>(`/pipeline/runs/${runId}/markets/${marketId}`)
export const triggerRun = (top_n?: number) =>
  request<PipelineRunAccepted>('/pipeline/run', {
    method: 'POST',
    body: JSON.stringify({ top_n }),
  })
export const cancelRun = (id: string) =>
  request<void>(`/pipeline/runs/${id}/cancel`, { method: 'POST' })

// Markets
export const fetchMarkets = () => request<any[]>('/markets')
export const fetchMarket = (id: string) => request<any>(`/markets/${id}`)

// Decisions
export const fetchDecisions = (params?: string) =>
  request<any[]>(`/decisions${params ? '?' + params : ''}`)

// Bets
export const fetchBets = (params?: string) =>
  request<any[]>(`/bets${params ? '?' + params : ''}`)
export const resolveBet = (id: string, pnl: number) =>
  request<any>(`/bets/${id}/resolve`, { method: 'POST', body: JSON.stringify({ pnl }) })
export const retryBet = (id: string) =>
  request<any>(`/bets/${id}/retry`, { method: 'POST' })
export const syncBetSettlements = () =>
  request<any>('/bets/sync-settlements', { method: 'POST' })

// Wallet (matches backend wallet_service.get_snapshot keys)
export type WalletSummary = {
  clob_configured?: boolean
  wallet_address?: string | null
  clob_collateral_balance_usd?: number | null
  clob_collateral_allowance_usd?: number | null
  positions_market_value_usd?: number | null
  open_positions_count?: number | null
  total_portfolio_usd?: number | null
  gamma_host?: string
}

export const fetchWalletSummary = () => request<WalletSummary>('/wallet/summary')

// Settings
export const fetchSettings = () => request<Record<string, any[]>>('/settings')
export const updateSetting = (category: string, key: string, value: any) =>
  request<any>(`/settings/${category}/${key}`, {
    method: 'PUT',
    body: JSON.stringify({ value }),
  })
export const resetSettingsDefaults = () =>
  request<void>('/settings/reset-defaults', { method: 'POST' })

// Prompts
export const fetchPrompts = () => request<any[]>('/prompts')
export const updatePrompt = (name: string, template: string) =>
  request<any>(`/prompts/${name}`, { method: 'PUT', body: JSON.stringify({ template }) })
export const resetPromptsDefaults = () =>
  request<void>('/prompts/reset-defaults', { method: 'POST' })

// Scheduler
export const fetchScheduler = () => request<any>('/scheduler')
export const updateScheduler = (cfg: any) =>
  request<any>('/scheduler', { method: 'PUT', body: JSON.stringify(cfg) })

// Stats / Token usage
export const fetchTokenStats = (period: 'today' | '7d' | '30d' | 'all' = 'today') =>
  request<any>(`/stats/tokens?period=${period}`)
export const resetRuntimeData = () =>
  request<any>('/stats/runtime-reset', { method: 'POST' })

// System / diagnostics (backend egress IP)
export type PolymarketServerGeoblock = {
  blocked: boolean
  ip?: string
  country?: string
  region?: string
}

export const fetchPolymarketServerGeoblock = () =>
  request<PolymarketServerGeoblock>('/system/polymarket-geoblock')

export type PolymarketClobHealth = {
  ok: boolean
  latency_ms: number
  wallet_address?: string | null
  has_balance_payload: boolean
}

export const fetchPolymarketClobHealth = () =>
  request<PolymarketClobHealth>('/system/polymarket-clob-health')

// Copy trading
export type CopyTradingStatus = {
  worker_running: boolean
  enabled: boolean
  live: boolean
  binary_only: boolean
  target_wallet: string | null
  target_wallets?: string[]
  active_targets_count?: number
  poll_seconds: number
  activity_limit: number
  min_bet_usd: number
  slippage: number
  max_orders_per_hour: number
  min_balance_buffer_usd: number
  orders_last_hour: number
  processed_events_size: number
  last_loop_at?: string | null
  next_check_at?: string | null
  seconds_until_next_check?: number | null
  last_error?: string | null
  last_signals_count: number
  target_open_positions_count?: number | null
  target_recent_activity_count?: number | null
  target_recent_buy_trades_count?: number | null
  target_recent_buy_share_pct?: number | null
  target_open_positions_cash_pnl_sum?: number | null
  target_last_buy_at?: string | null
  target_last_buy_age_seconds?: number | null
  target_stats_updated_at?: string | null
  target_stats_error?: string | null
  targets?: Array<{
    wallet: string
    open_positions_count?: number | null
    recent_activity_count?: number | null
    recent_buy_trades_count?: number | null
    recent_buy_share_pct?: number | null
    open_positions_cash_pnl_sum?: number | null
    last_buy_at?: string | null
    last_buy_age_seconds?: number | null
    updated_at?: string | null
    error?: string | null
    copied_count?: number
    skipped_count?: number
    skip_reasons?: Record<string, number>
    last_fetch_ok_at?: string | null
    last_fetch_error?: string | null
    last_fetch_error_at?: string | null
    fetch_error_streak?: number
    next_retry_in_seconds?: number | null
    health?: 'healthy' | 'degraded'
  }>
  recent_events: Array<Record<string, unknown>>
}

export const fetchCopyTradingStatus = () =>
  request<CopyTradingStatus>('/copy-trading/status')

export const startCopyTrading = () =>
  request<CopyTradingStatus>('/copy-trading/start', { method: 'POST' })

export const stopCopyTrading = () =>
  request<CopyTradingStatus>('/copy-trading/stop', { method: 'POST' })
