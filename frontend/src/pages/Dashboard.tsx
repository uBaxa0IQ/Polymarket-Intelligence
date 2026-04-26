import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from 'recharts'
import {
  fetchSummary, fetchPnlChart, fetchRecentActivity, fetchWalletSummary,
  fetchTokenStats, fetchScheduler, fetchMarket, triggerRun,
} from '../api/client'
import { fmtUsd, fmtPct, fmtDate, timeAgo, pnlColor, betStatusColor, fmtTokens } from '../lib/utils'
import { useExecution } from '../components/Layout'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useToast } from '../components/ToastProvider'
import { ErrorState, LoadingState, TableSkeleton } from '../components/QueryStates'

function MetricCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-panel border border-border rounded p-4">
      <p className="text-xs text-muted mb-1">{label}</p>
      <p className="text-xl font-mono font-medium text-white">{value}</p>
      {sub && <p className="text-xs text-muted mt-0.5">{sub}</p>}
    </div>
  )
}

export default function Dashboard() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { pushToast } = useToast()
  const { executionEnabled } = useExecution()
  const [chartPeriod, setChartPeriod] = useState<'7d' | '30d' | 'all'>('7d')
  const [nowTs, setNowTs] = useState(() => Date.now())
  const [modalBet, setModalBet] = useState<any | null>(null)

  useEffect(() => {
    const t = window.setInterval(() => setNowTs(Date.now()), 1000)
    return () => window.clearInterval(t)
  }, [])

  useEffect(() => {
    if (!modalBet) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setModalBet(null)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [modalBet])

  const { data: summary, isLoading: summaryLoading, isError: summaryError, refetch: refetchSummary } = useQuery({
    queryKey: ['summary'],
    queryFn: fetchSummary,
    refetchInterval: 15_000,
  })
  const { data: chart = [], isLoading: chartLoading, isError: chartError, refetch: refetchChart } = useQuery({
    queryKey: ['pnl-chart', chartPeriod],
    queryFn: () => fetchPnlChart(chartPeriod),
  })
  const { data: activity = [], isLoading: activityLoading, isError: activityError, refetch: refetchActivity } = useQuery({
    queryKey: ['activity'],
    queryFn: fetchRecentActivity,
    refetchInterval: 10_000,
  })
  const { data: wallet, isLoading: walletLoading, isError: walletError, refetch: refetchWallet } = useQuery({
    queryKey: ['wallet'],
    queryFn: fetchWalletSummary,
    refetchInterval: 30_000,
  })
  const { data: tokens, isLoading: tokensLoading, isError: tokensError, refetch: refetchTokens } = useQuery({
    queryKey: ['tokens', 'today'],
    queryFn: () => fetchTokenStats('today'),
    refetchInterval: 60_000,
  })
  const { data: scheduler } = useQuery({
    queryKey: ['scheduler'],
    queryFn: fetchScheduler,
    refetchInterval: 30_000,
  })
  const { data: marketMeta, isError: marketError, refetch: refetchMarket } = useQuery({
    queryKey: ['market', modalBet?.market_id],
    queryFn: () => fetchMarket(modalBet.market_id),
    enabled: !!modalBet?.market_id,
  })

  const runMut = useMutation({
    mutationFn: triggerRun,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['runs'] })
      pushToast('Pipeline run started.', 'success')
      navigate(`/pipeline/${data.run_id}`)
    },
    onError: (err: any) => pushToast(err?.message || 'Failed to start pipeline run.', 'error'),
  })

  const totalPnl = summary?.total_pnl ?? null
  const winRate = summary?.win_rate ?? null
  const walletBalance = wallet?.clob_collateral_balance_usd ?? null
  const openPositions = wallet?.open_positions_count ?? null

  const chartData = chart.map((p: any) => ({
    date: new Date(p.date || p.resolved_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    pnl: p.cumulative ?? p.cumulative_pnl ?? p.pnl ?? 0,
  }))

  const todayCost = tokens?.totals?.cost_usd ?? null
  const schedulerEnabled = Boolean(scheduler?.enabled)
  const nextPipelineRunIso = (() => {
    const jobs = Array.isArray(scheduler?.jobs) ? scheduler.jobs : []
    return jobs.find((j: any) => j?.id === 'pipeline_main')?.next_run ?? null
  })()

  function formatCountdown(nextIso: string | null | undefined): string {
    if (!nextIso) return '—'
    const ms = new Date(nextIso).getTime() - nowTs
    if (ms <= 0) return 'starting soon'
    const totalSec = Math.floor(ms / 1000)
    const h = Math.floor(totalSec / 3600)
    const m = Math.floor((totalSec % 3600) / 60)
    const s = totalSec % 60
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }

  function polymarketLinks() {
    const fromActivity = modalBet?.polymarket_url ? String(modalBet.polymarket_url).trim() : ''
    if (fromActivity) return { marketUrl: fromActivity }
    const slug = marketMeta?.market_slug ? String(marketMeta.market_slug).trim() : null
    return {
      marketUrl: slug ? `https://polymarket.com/market/${encodeURIComponent(slug)}` : null,
    }
  }

  return (
    <div className="space-y-6">
      {(summaryLoading || walletLoading) && <LoadingState label="Loading dashboard..." />}
      {activityLoading && <TableSkeleton rows={5} columns={5} />}
      {(summaryError || chartError || activityError || walletError || tokensError) && (
        <ErrorState
          message="Failed to load dashboard data."
          onRetry={() => {
            refetchSummary()
            refetchChart()
            refetchActivity()
            refetchWallet()
            refetchTokens()
          }}
        />
      )}
      {/* Metric strip */}
      <div className="grid grid-cols-4 gap-3">
        <MetricCard
          label="Wallet Balance"
          value={walletBalance != null ? fmtUsd(walletBalance) : '—'}
          sub="CLOB collateral"
        />
        <MetricCard label="Open Positions" value={openPositions != null ? String(openPositions) : '—'} />
        <MetricCard
          label="Total P&L"
          value={totalPnl != null ? fmtUsd(totalPnl) : '—'}
          sub="all resolved bets"
        />
        <MetricCard
          label="Win Rate"
          value={winRate != null ? fmtPct(winRate) : '—'}
          sub="live bets only"
        />
      </div>

      {/* Main 2-col */}
      <div className="grid grid-cols-3 gap-4">
        {/* Left: chart + recent bets */}
        <div className="col-span-2 space-y-4">
          {/* P&L Chart */}
          <div className="bg-panel border border-border rounded p-4">
            <div className="flex items-center justify-between mb-3">
              <p className="text-sm font-medium text-white">Cumulative P&L</p>
              <div className="flex gap-1">
                {(['7d', '30d', 'all'] as const).map(p => (
                  <button
                    key={p}
                    onClick={() => setChartPeriod(p)}
                    className={`px-2 py-0.5 rounded text-xs transition-colors ${
                      chartPeriod === p
                        ? 'bg-accent text-white'
                        : 'text-muted hover:text-white'
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
            {chartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={180}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#22c55e" stopOpacity={0.15} />
                      <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: '#64748b', fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={v => `$${v}`} />
                  <Tooltip
                    contentStyle={{ background: '#1a1a24', border: '1px solid #2a2a3a', borderRadius: 4 }}
                    labelStyle={{ color: '#e2e8f0', fontSize: 11 }}
                    itemStyle={{ color: '#22c55e', fontSize: 11 }}
                    formatter={(v: number) => [`$${v.toFixed(2)}`, 'P&L']}
                  />
                  <Area type="monotone" dataKey="pnl" stroke="#22c55e" strokeWidth={1.5} fill="url(#pnlGrad)" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-44 flex items-center justify-center text-muted text-sm">No data yet</div>
            )}
          </div>

          {/* Recent bets */}
          <div className="bg-panel border border-border rounded">
            <div className="px-4 py-3 border-b border-border">
              <p className="text-sm font-medium text-white">Recent Bets</p>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left px-4 py-2 text-xs text-muted font-normal">Market</th>
                  <th className="text-left px-4 py-2 text-xs text-muted font-normal">Side</th>
                  <th className="text-right px-4 py-2 text-xs text-muted font-normal">Amount</th>
                  <th className="text-left px-4 py-2 text-xs text-muted font-normal">Status</th>
                  <th className="text-right px-4 py-2 text-xs text-muted font-normal">P&L</th>
                </tr>
              </thead>
              <tbody>
                {(activity as any[])
                  .filter((e: any) => e.type === 'bet')
                  .slice(0, 10)
                  .map((b: any, i: number) => (
                  <tr
                    key={b.id ?? i}
                    className="border-b border-border/50 hover:bg-card/50 transition-colors cursor-pointer"
                    onClick={() => setModalBet(b)}
                  >
                    <td className="px-4 py-2 text-white max-w-xs truncate">
                      {b.question || b.market_id}
                    </td>
                    <td className={`px-4 py-2 font-mono text-xs uppercase ${b.side === 'yes' ? 'text-green' : 'text-red'}`}>
                      {b.side}
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-xs text-white">
                      {fmtUsd(b.amount_usd)}
                    </td>
                    <td className={`px-4 py-2 text-xs ${betStatusColor(b.status)}`}>
                      {b.status?.toUpperCase()}
                    </td>
                    <td className={`px-4 py-2 text-right font-mono text-xs ${pnlColor(b.pnl)}`}>
                      {b.pnl != null ? fmtUsd(b.pnl) : '—'}
                    </td>
                  </tr>
                ))}
                {(activity as any[]).filter((e: any) => e.type === 'bet').length === 0 && (
                  <tr><td colSpan={5} className="px-4 py-6 text-center text-muted text-sm">No bets yet</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right: pipeline status + token usage */}
        <div className="space-y-4">
          {/* Pipeline status */}
          <div className="bg-panel border border-border rounded p-4 space-y-3">
            <p className="text-sm font-medium text-white">Pipeline</p>
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs">
                <span className="text-muted">Last run</span>
                <span className="text-white">{timeAgo(summary?.last_run_at)}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-muted">Status</span>
                <span className="text-white">{summary?.last_run_status || '—'}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-muted">Auto-run</span>
                <span className="text-white">{schedulerEnabled ? 'ON' : 'OFF'}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-muted">Execution</span>
                <span className={executionEnabled ? 'text-indigo-300' : 'text-muted'}>
                  {executionEnabled ? 'LIVE' : 'DRY RUN'}
                </span>
              </div>
            </div>
            {schedulerEnabled ? (
              <div className="rounded border border-border bg-card px-3 py-2">
                <p className="text-xs text-muted">Next scheduled run in</p>
                <p className="text-sm text-white font-mono mt-0.5">{formatCountdown(nextPipelineRunIso)}</p>
                {nextPipelineRunIso && (
                  <p className="text-xs text-muted mt-0.5">at {fmtDate(nextPipelineRunIso)}</p>
                )}
              </div>
            ) : (
              <button
                onClick={() => runMut.mutate(undefined)}
                disabled={runMut.isPending}
                className="w-full bg-accent hover:bg-indigo-500 disabled:opacity-50 text-white text-sm py-2 rounded transition-colors"
              >
                {runMut.isPending ? 'Starting...' : 'Run Now'}
              </button>
            )}
          </div>

          {/* Wallet detail */}
          {wallet && (
            <div className="bg-panel border border-border rounded p-4 space-y-2">
              <p className="text-sm font-medium text-white">Wallet</p>
              <div className="space-y-1">
                {wallet.wallet_address && (
                  <p className="text-xs font-mono text-muted truncate" title={wallet.wallet_address}>
                    {wallet.wallet_address}
                  </p>
                )}
                <div className="flex justify-between text-xs">
                  <span className="text-muted">Collateral</span>
                  <span className="text-white font-mono">{fmtUsd(wallet.clob_collateral_balance_usd)}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-muted">Positions</span>
                  <span className="text-white font-mono">{fmtUsd(wallet.positions_market_value_usd)}</span>
                </div>
              </div>
            </div>
          )}

          {/* Token usage today */}
          {tokens && (
            <div className="bg-panel border border-border rounded p-4 space-y-2">
              <p className="text-sm font-medium text-white">Tokens Today</p>
              <div className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-muted">Input</span>
                  <span className="text-white font-mono">{fmtTokens(tokens.totals?.input_tokens)}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-muted">Output</span>
                  <span className="text-white font-mono">{fmtTokens(tokens.totals?.output_tokens)}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-muted">Cost</span>
                  <span className="text-white font-mono">
                    {todayCost != null ? `$${todayCost.toFixed(4)}` : '—'}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
      {modalBet && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70"
          role="dialog"
          aria-modal="true"
          onClick={() => setModalBet(null)}
        >
          <div
            className="bg-panel border border-border rounded max-w-2xl w-full max-h-[90vh] overflow-y-auto shadow-xl"
            onClick={e => e.stopPropagation()}
          >
            <div className="sticky top-0 bg-panel/95 border-b border-border px-4 py-3 flex justify-between items-center">
              <h3 className="text-sm font-medium text-white">Bet</h3>
              <button type="button" onClick={() => setModalBet(null)} className="text-muted hover:text-white text-sm">
                Close
              </button>
            </div>
            <div className="p-4 space-y-4">
              {marketError ? (
                <ErrorState message="Failed to load market details." onRetry={() => refetchMarket()} />
              ) : marketMeta ? (
                <p className="text-white text-sm">{marketMeta.question}</p>
              ) : modalBet?.question ? (
                <p className="text-white text-sm">{modalBet.question}</p>
              ) : (
                <p className="text-muted text-sm">Loading...</p>
              )}
              <div className="flex items-center gap-2">
                {polymarketLinks().marketUrl && (
                  <a
                    href={polymarketLinks().marketUrl!}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center rounded border border-border px-3 py-1.5 text-xs text-indigo-300 hover:text-white hover:border-accent"
                  >
                    Open on Polymarket
                  </a>
                )}
              </div>

              <div className="grid grid-cols-2 gap-3 border border-border rounded p-3 text-sm">
                <div>
                  <p className="text-muted">Amount</p>
                  <p className="text-white font-medium">{fmtUsd(modalBet.amount_usd)}</p>
                </div>
                <div>
                  <p className="text-muted">P&L</p>
                  <p className={`font-medium ${pnlColor(modalBet.pnl)}`}>
                    {modalBet.pnl != null ? fmtUsd(modalBet.pnl) : '—'}
                  </p>
                </div>
                <div>
                  <p className="text-muted">Side</p>
                  <p className="text-white">{String(modalBet.side || '—').toUpperCase()}</p>
                </div>
                <div>
                  <p className="text-muted">Status</p>
                  <p className={betStatusColor(modalBet.status)}>{modalBet.status || '—'}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
