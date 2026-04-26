import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  fetchBets,
  fetchDecisions,
  fetchMarket,
  retryBet,
} from '../api/client'
import { fmt, fmtDate, fmtMarketEndDate, gapColor, pct, betStatusColor, fmtUsd, pnlColor } from '../lib/utils'
import DebateViewer from '../components/DebateViewer'
import { ErrorState, LoadingState, TableSkeleton } from '../components/QueryStates'

type TabKey = 'open' | 'history' | 'stats'

export default function Bets() {
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<TabKey>('open')
  const [hideDryInHistory, setHideDryInHistory] = useState(false)
  const [modalBet, setModalBet] = useState<any | null>(null)
  const [showPipelineDetail, setShowPipelineDetail] = useState(false)
  const [showBetDetails, setShowBetDetails] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [retryError, setRetryError] = useState<string | null>(null)

  const { data: openBets = [], isLoading: openLoading, isError: openError, refetch: refetchOpen } = useQuery({
    queryKey: ['bets', 'open'],
    queryFn: () => fetchBets('resolved=false&limit=500'),
    enabled: tab === 'open',
  })

  const { data: historyBets = [], isLoading: histLoading, isError: histError, refetch: refetchHistory } = useQuery({
    queryKey: ['bets', 'history', hideDryInHistory],
    queryFn: () =>
      fetchBets(
        hideDryInHistory
          ? 'resolved=true&exclude_dry_run=true&limit=500'
          : 'resolved=true&limit=500',
      ),
    enabled: tab === 'history' || tab === 'stats',
  })

  const { data: skipped = [], isLoading: skipLoading, isError: skipError, refetch: refetchSkipped } = useQuery({
    queryKey: ['decisions', 'skip'],
    queryFn: () => fetchDecisions('action=skip&limit=200'),
    enabled: tab === 'stats',
  })

  const { data: marketMeta, isError: marketError, refetch: refetchMarket } = useQuery({
    queryKey: ['market', modalBet?.market_id],
    queryFn: () => fetchMarket(modalBet.market_id),
    enabled: !!modalBet?.market_id,
  })

  const sortedOpenBets = useMemo(() => sortByEndDateWithFallback(openBets as any[]), [openBets])
  const sortedHistoryBets = useMemo(() => sortByEndDateWithFallback(historyBets as any[]), [historyBets])

  useEffect(() => {
    if (!modalBet) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setModalBet(null)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [modalBet])

  const stats = useMemo(() => {
    const all = sortedHistoryBets as any[]
    const live = all.filter((b: any) => b.status !== 'dry_run')
    const slice = (rows: any[]) => rows.filter((b: any) => b.resolved && b.pnl != null)

    function agg(rows: any[]) {
      const r = slice(rows)
      const n = r.length
      const wins = r.filter((b: any) => (b.pnl ?? 0) > 0).length
      const pnlSum = r.reduce((s: number, b: any) => s + (Number(b.pnl) || 0), 0)
      const wr = n ? wins / n : null
      const bySide = (side: string) => {
        const sub = r.filter((b: any) => b.side === side)
        const sn = sub.length
        const sw = sub.filter((b: any) => (b.pnl ?? 0) > 0).length
        const sp = sub.reduce((s: number, b: any) => s + (Number(b.pnl) || 0), 0)
        return { n: sn, wr: sn ? sw / sn : null, pnl: sp }
      }
      return {
        n,
        winRate: wr,
        totalPnl: pnlSum,
        avg: n ? pnlSum / n : null,
        best: n ? Math.max(...r.map((b: any) => Number(b.pnl) || 0)) : null,
        worst: n ? Math.min(...r.map((b: any) => Number(b.pnl) || 0)) : null,
        yes: bySide('yes'),
        no: bySide('no'),
      }
    }

    return { live: agg(live), all: agg(all), skipped: skipped.length }
  }, [sortedHistoryBets, skipped])

  const tabBtn = (k: TabKey, label: string) => (
    <button
      type="button"
      key={k}
      onClick={() => setTab(k)}
      className={`text-sm px-4 py-2 rounded-lg transition-colors ${
        tab === k ? 'bg-accent text-white font-medium' : 'bg-card text-muted hover:text-white border border-border'
      }`}
    >
      {label}
    </button>
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-white font-medium text-lg">Bets</h1>
      </div>

      <div className="flex flex-wrap gap-2">
        {tabBtn('open', 'Open Positions')}
        {tabBtn('history', 'History')}
        {tabBtn('stats', 'Statistics')}
      </div>

      {tab === 'open' &&
        (openLoading ? (
          <TableSkeleton rows={7} columns={8} />
        ) : openError ? (
          <ErrorState message="Failed to load open positions." onRetry={() => refetchOpen()} />
        ) : (
          <div className="bg-panel border border-border rounded overflow-x-auto">
            <table className="w-full text-sm min-w-[720px]">
              <thead>
                <tr className="border-b border-border text-muted text-xs">
                  <th className="px-4 py-2 text-left">Market</th>
                  <th className="px-4 py-2 text-left">Source</th>
                  <th className="px-4 py-2 text-left">Side</th>
                  <th className="px-4 py-2 text-right">Amount</th>
                  <th className="px-4 py-2 text-right">Price</th>
                  <th className="px-4 py-2 text-right">Shares</th>
                  <th className="px-4 py-2 text-left">Placed</th>
                  <th className="px-4 py-2 text-left">End date</th>
                  <th className="px-4 py-2 text-left">Status</th>
                </tr>
              </thead>
              <tbody>
                {sortedOpenBets.map((b: any) => (
                  <tr
                    key={b.id}
                    className="border-b border-border/50 hover:bg-card/40 cursor-pointer"
                    onClick={() => {
                      setModalBet(b)
                      setShowPipelineDetail(false)
                      setShowBetDetails(false)
                      setRetrying(false)
                      setRetryError(null)
                    }}
                  >
                    <td className="px-4 py-2 text-white text-xs max-w-xs truncate" title={b.market_id}>
                      {b.question || b.market_question || b.market_id}
                    </td>
                    <td className="px-4 py-2 text-xs uppercase text-muted">{String(b.source || 'pipeline')}</td>
                    <td className="px-4 py-2">
                      <span
                        className={`text-xs px-2 py-0.5 rounded font-medium ${
                          b.side === 'yes' ? 'bg-green/20 text-green' : 'bg-red/20 text-red'
                        }`}
                      >
                        {b.side?.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-xs text-white">${fmt(b.amount_usd)}</td>
                    <td className="px-4 py-2 text-right font-mono text-xs text-muted">
                      {b.price != null ? fmt(b.price, 3) : '—'}
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-xs text-muted">
                      {b.shares != null ? fmt(b.shares, 2) : '—'}
                    </td>
                    <td className="px-4 py-2 text-muted text-xs">{fmtDate(b.placed_at)}</td>
                    <td className="px-4 py-2 text-muted text-xs">
                      {fmtMarketEndDate(b.market_end_date, b.question || b.market_question)}
                    </td>
                    <td className={`px-4 py-2 text-xs ${betStatusColor(b.status)}`}>{b.status?.toUpperCase()}</td>
                  </tr>
                ))}
                {sortedOpenBets.length === 0 && (
                  <tr><td colSpan={9} className="px-4 py-8 text-center text-muted text-sm">No open positions.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        ))}

      {tab === 'history' && (
        <div className="space-y-2">
          <label className="inline-flex items-center gap-3 text-xs text-muted cursor-pointer select-none">
            <span
              className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                hideDryInHistory ? 'bg-accent' : 'bg-border'
              }`}
            >
              <input
                type="checkbox"
                checked={hideDryInHistory}
                onChange={e => setHideDryInHistory(e.target.checked)}
                className="peer sr-only"
              />
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  hideDryInHistory ? 'translate-x-4' : 'translate-x-0.5'
                }`}
              />
            </span>
            Hide dry run from history list
          </label>
          {histLoading ? (
            <TableSkeleton rows={7} columns={8} />
          ) : histError ? (
            <ErrorState message="Failed to load bet history." onRetry={() => refetchHistory()} />
          ) : (
            <div className="bg-panel border border-border rounded overflow-x-auto">
              <table className="w-full text-sm min-w-[800px]">
                <thead>
                  <tr className="border-b border-border text-muted text-xs">
                    <th className="px-4 py-2 text-left">Market</th>
                    <th className="px-4 py-2 text-left">Source</th>
                    <th className="px-4 py-2 text-left">Side</th>
                    <th className="px-4 py-2 text-right">Amount</th>
                    <th className="px-4 py-2 text-right">Price</th>
                    <th className="px-4 py-2 text-left">Outcome</th>
                    <th className="px-4 py-2 text-right">P&L</th>
                    <th className="px-4 py-2 text-left">End date</th>
                    <th className="px-4 py-2 text-left">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedHistoryBets.map((b: any) => (
                    <tr key={b.id} className="border-b border-border/50 hover:bg-card/40">
                      <td className="px-4 py-2 text-xs text-white max-w-xs truncate">{b.question || b.market_question || b.market_id}</td>
                      <td className="px-4 py-2 text-xs uppercase text-muted">{String(b.source || 'pipeline')}</td>
                      <td className="px-4 py-2 text-xs uppercase text-muted">{b.side}</td>
                      <td className="px-4 py-2 text-right font-mono text-xs">${fmt(b.amount_usd)}</td>
                      <td className="px-4 py-2 text-right font-mono text-xs text-muted">
                        {b.price != null ? fmt(b.price, 3) : '—'}
                      </td>
                      <td className="px-4 py-2 text-xs text-muted">
                        {(b.pnl ?? 0) > 0 ? 'Won' : (b.pnl ?? 0) < 0 ? 'Lost' : '—'}
                      </td>
                      <td className={`px-4 py-2 text-right font-mono text-xs ${pnlColor(b.pnl)}`}>
                        {b.pnl != null ? fmtUsd(b.pnl) : '—'}
                      </td>
                      <td className="px-4 py-2 text-muted text-xs">
                        {fmtMarketEndDate(b.market_end_date, b.question || b.market_question)}
                      </td>
                      <td className="px-4 py-2 text-muted text-xs">{fmtDate(b.resolved_at || b.placed_at)}</td>
                    </tr>
                  ))}
                  {sortedHistoryBets.length === 0 && (
                    <tr>
                      <td colSpan={9} className="px-4 py-8 text-center text-muted text-sm">
                        No resolved bets.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === 'stats' && (
        <div className="space-y-4">
          {skipLoading ? (
            <LoadingState label="Loading statistics..." />
          ) : skipError ? (
            <ErrorState message="Failed to load statistics." onRetry={() => refetchSkipped()} />
          ) : (
            <div className="grid md:grid-cols-2 gap-4">
              <div className="bg-panel border border-border rounded p-4 space-y-2">
                <p className="text-sm font-medium text-white">Live bets only</p>
                <p className="text-xs text-muted">Excludes dry_run</p>
                <dl className="text-xs space-y-1 text-muted">
                  <div className="flex justify-between">
                    <dt>Win rate</dt>
                    <dd className="text-white font-mono">
                      {stats.live.winRate != null ? `${(stats.live.winRate * 100).toFixed(1)}%` : '—'}
                    </dd>
                  </div>
                  <div className="flex justify-between">
                    <dt>Total bets</dt>
                    <dd className="text-white font-mono">{stats.live.n}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt>Avg P&L / bet</dt>
                    <dd className="text-white font-mono">
                      {stats.live.avg != null ? fmtUsd(stats.live.avg) : '—'}
                    </dd>
                  </div>
                  <div className="flex justify-between">
                    <dt>Total P&L</dt>
                    <dd className={`font-mono ${pnlColor(stats.live.totalPnl)}`}>{fmtUsd(stats.live.totalPnl)}</dd>
                  </div>
                </dl>
              </div>
              <div className="bg-panel border border-border rounded p-4 space-y-2">
                <p className="text-sm font-medium text-white">All (incl. dry run)</p>
                <dl className="text-xs space-y-1 text-muted">
                  <div className="flex justify-between">
                    <dt>Win rate</dt>
                    <dd className="text-white font-mono">
                      {stats.all.winRate != null ? `${(stats.all.winRate * 100).toFixed(1)}%` : '—'}
                    </dd>
                  </div>
                  <div className="flex justify-between">
                    <dt>Total bets</dt>
                    <dd className="text-white font-mono">{stats.all.n}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt>Total P&L</dt>
                    <dd className={`font-mono ${pnlColor(stats.all.totalPnl)}`}>{fmtUsd(stats.all.totalPnl)}</dd>
                  </div>
                </dl>
              </div>
            </div>
          )}
          <div className="bg-panel border border-border rounded p-4">
            <p className="text-sm font-medium text-white mb-2">By side (live)</p>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-muted border-b border-border">
                  <th className="text-left py-2">Side</th>
                  <th className="text-right py-2">Bets</th>
                  <th className="text-right py-2">Win rate</th>
                  <th className="text-right py-2">P&L</th>
                </tr>
              </thead>
              <tbody>
                {(['yes', 'no'] as const).map(side => {
                  const s = side === 'yes' ? stats.live.yes : stats.live.no
                  return (
                    <tr key={side} className="border-b border-border/40">
                      <td className="py-2 text-white uppercase">{side}</td>
                      <td className="py-2 text-right font-mono text-muted">{s.n}</td>
                      <td className="py-2 text-right font-mono text-muted">
                        {s.wr != null ? `${(s.wr * 100).toFixed(0)}%` : '—'}
                      </td>
                      <td className={`py-2 text-right font-mono ${pnlColor(s.pnl)}`}>{fmtUsd(s.pnl)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted">Skip decisions (recent): {stats.skipped}</p>
        </div>
      )}

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
              ) : (
                <p className="text-muted text-sm">Loading...</p>
              )}
              <div className="flex items-center gap-2">
                {(() => {
                  const u =
                    (modalBet.polymarket_url && String(modalBet.polymarket_url).trim()) ||
                    (marketMeta?.market_slug
                      ? `https://polymarket.com/market/${encodeURIComponent(String(marketMeta.market_slug).trim())}`
                      : null)
                  return u ? (
                    <a
                      href={u}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center rounded border border-border px-3 py-1.5 text-xs text-indigo-300 hover:text-white hover:border-accent"
                    >
                      Open on Polymarket
                    </a>
                  ) : null
                })()}
              </div>

              <div className="grid grid-cols-2 gap-3 border border-border rounded p-3 text-sm">
                <div>
                  <p className="text-muted">Amount</p>
                  <p className="text-white font-medium">${fmt(modalBet.amount_usd)}</p>
                </div>
                <div>
                  <p className="text-muted">P&L</p>
                  <p className={`font-medium ${pnlColor(modalBet.pnl)}`}>{modalBet.pnl != null ? fmtUsd(modalBet.pnl) : '—'}</p>
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

              {modalBet.status === 'failed' && (
                <div className="border border-red/30 rounded p-3 space-y-2 bg-red/5">
                  <p className="text-xs text-red font-medium">Bet failed</p>
                  {modalBet.error_message && (
                    <p className="text-xs text-muted font-mono break-all">{modalBet.error_message}</p>
                  )}
                  {retryError && (
                    <p className="text-xs text-red break-all">{retryError}</p>
                  )}
                  <button
                    type="button"
                    disabled={retrying}
                    onClick={async () => {
                      setRetrying(true)
                      setRetryError(null)
                      try {
                        const newBet = await retryBet(modalBet.id)
                        queryClient.invalidateQueries({ queryKey: ['bets'] })
                        setModalBet(newBet)
                        setRetrying(false)
                      } catch (err: any) {
                        setRetryError(err?.message ?? 'Retry failed')
                        setRetrying(false)
                      }
                    }}
                    className="text-xs px-3 py-1.5 rounded bg-accent text-white hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {retrying ? 'Retrying...' : 'Retry Bet'}
                  </button>
                </div>
              )}

              <div className="space-y-2">
                <button
                  type="button"
                  onClick={() => setShowBetDetails(s => !s)}
                  className="text-sm text-muted hover:text-white"
                >
                  {showBetDetails ? 'Hide details' : 'Show details'}
                </button>
                {showBetDetails && (
                  <dl className="border border-border rounded p-3 space-y-2 text-sm">
                    <div className="flex justify-between gap-2">
                      <dt className="text-muted">Price</dt>
                      <dd className="text-white">{modalBet.price != null ? fmt(modalBet.price, 3) : '—'}</dd>
                    </div>
                    <div className="flex justify-between gap-2">
                      <dt className="text-muted">Shares</dt>
                      <dd className="text-white">{modalBet.shares != null ? fmt(modalBet.shares, 2) : '—'}</dd>
                    </div>
                    <div className="flex justify-between gap-2">
                      <dt className="text-muted">Gap</dt>
                      <dd className={gapColor(modalBet.gap)}>{modalBet.gap != null ? fmt(modalBet.gap, 3) : '—'}</dd>
                    </div>
                    <div className="flex justify-between gap-2">
                      <dt className="text-muted">p_yes / p_mkt</dt>
                      <dd className="text-white">
                        {modalBet.p_yes != null ? pct(modalBet.p_yes) : '—'} /{' '}
                        {modalBet.p_market != null ? pct(modalBet.p_market) : '—'}
                      </dd>
                    </div>
                    <div className="flex justify-between gap-2">
                      <dt className="text-muted">Market ID</dt>
                      <dd className="text-white font-mono text-xs break-all">{modalBet.market_id || '—'}</dd>
                    </div>
                  </dl>
                )}
              </div>

              <div className="border-t border-border pt-3">
                <button
                  type="button"
                  onClick={() => setShowPipelineDetail(s => !s)}
                  className="text-sm text-muted hover:text-white mb-2"
                >
                  {showPipelineDetail ? 'Hide pipeline details' : 'Show pipeline details'}
                </button>
                {showPipelineDetail && modalBet.pipeline_run_id && modalBet.market_id && (
                  <DebateViewer runId={modalBet.pipeline_run_id} marketId={modalBet.market_id} />
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function sortByEndDateWithFallback(rows: any[]): any[] {
  return [...rows].sort((a, b) => {
    const endA = a?.market_end_date ? new Date(a.market_end_date).getTime() : 0
    const endB = b?.market_end_date ? new Date(b.market_end_date).getTime() : 0
    if (endA !== endB) return endB - endA
    const fallbackA = new Date(a?.resolved_at || a?.placed_at || 0).getTime()
    const fallbackB = new Date(b?.resolved_at || b?.placed_at || 0).getTime()
    return fallbackB - fallbackA
  })
}
