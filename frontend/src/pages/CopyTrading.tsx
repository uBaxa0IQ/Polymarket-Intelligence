import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import {
  fetchCopyTradingStatus,
  startCopyTrading,
  stopCopyTrading,
} from '../api/client'
import { LoadingState, ErrorState } from '../components/QueryStates'
import { useToast } from '../components/ToastProvider'

function fmtNum(v: unknown): string {
  if (typeof v !== 'number' || Number.isNaN(v)) return '—'
  return String(v)
}

function fmtTs(v: unknown): string {
  if (typeof v !== 'string' || !v) return '—'
  const d = new Date(v)
  if (Number.isNaN(d.getTime())) return v
  return d.toLocaleString()
}

function fmtSeconds(v: unknown): string {
  if (typeof v !== 'number' || Number.isNaN(v) || v <= 0) return '—'
  return `${Math.round(v)}s`
}

function fmtNextIn(v: unknown): string {
  if (typeof v !== 'number' || Number.isNaN(v) || v < 0) return '—'
  if (v === 0) return 'now'
  return `${Math.ceil(v)}s`
}

function fmtAgo(v: unknown): string {
  if (typeof v !== 'number' || Number.isNaN(v) || v < 0) return '—'
  if (v < 60) return `${v}s ago`
  const m = Math.floor(v / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  return `${d}d ago`
}

function fmtUsdSigned(v: unknown): string {
  if (typeof v !== 'number' || Number.isNaN(v)) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}$${v.toFixed(2)}`
}

export default function CopyTradingPage() {
  const qc = useQueryClient()
  const { pushToast } = useToast()
  const [openWallet, setOpenWallet] = useState<string | null>(null)
  const statusQ = useQuery({ queryKey: ['copy-trading-status'], queryFn: fetchCopyTradingStatus, refetchInterval: 5000 })

  const startMut = useMutation({
    mutationFn: startCopyTrading,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings'] })
      qc.invalidateQueries({ queryKey: ['copy-trading-status'] })
      pushToast('Copy-trading enabled', 'success')
    },
    onError: (e: any) => pushToast(e?.message || 'Failed to start copy-trading', 'error'),
  })

  const stopMut = useMutation({
    mutationFn: stopCopyTrading,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings'] })
      qc.invalidateQueries({ queryKey: ['copy-trading-status'] })
      pushToast('Copy-trading disabled', 'info')
    },
    onError: (e: any) => pushToast(e?.message || 'Failed to stop copy-trading', 'error'),
  })

  if (statusQ.isLoading) {
    return <LoadingState label="Loading copy-trading..." />
  }
  if (statusQ.isError) {
    return <ErrorState message="Failed to load copy-trading status." onRetry={() => statusQ.refetch()} />
  }
  const s = statusQ.data
  const runState = s?.enabled ? (s?.live ? 'LIVE' : 'DRY') : 'OFF'

  return (
    <div className="space-y-5 max-w-5xl">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold">Copy Trading</h2>
          <p className="text-sm text-gray-500">Standalone copier worker using Data API activity + CLOB execution.</p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => startMut.mutate()}
            disabled={startMut.isPending || !!s?.enabled}
            className="text-xs bg-emerald-700 hover:bg-emerald-600 disabled:opacity-60 text-white px-3 py-2 rounded-lg"
          >
            Enable
          </button>
          <button
            type="button"
            onClick={() => stopMut.mutate()}
            disabled={stopMut.isPending || !s?.enabled}
            className="text-xs bg-gray-800 hover:bg-gray-700 disabled:opacity-60 border border-gray-700 text-gray-200 px-3 py-2 rounded-lg"
          >
            Disable
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-xs">
        <div className="bg-gray-900/40 border border-gray-800 rounded-lg p-3"><p className="text-gray-500">Mode</p><p className="mt-1 text-gray-200">{runState}</p></div>
        <div className="bg-gray-900/40 border border-gray-800 rounded-lg p-3"><p className="text-gray-500">Worker</p><p className="mt-1 text-gray-200">{s?.worker_running ? 'running' : 'stopped'}</p></div>
        <div className="bg-gray-900/40 border border-gray-800 rounded-lg p-3"><p className="text-gray-500">Tracked wallets</p><p className="mt-1 text-gray-200">{fmtNum(s?.active_targets_count)}</p></div>
        <div className="bg-gray-900/40 border border-gray-800 rounded-lg p-3"><p className="text-gray-500">Orders (1h)</p><p className="mt-1 text-gray-200">{fmtNum(s?.orders_last_hour)}</p></div>
        <div className="bg-gray-900/40 border border-gray-800 rounded-lg p-3 col-span-2 md:col-span-1"><p className="text-gray-500">Check interval</p><p className="mt-1 text-gray-200">{fmtSeconds(s?.poll_seconds)}</p><p className="text-[10px] text-gray-500 mt-1">next in: {fmtNextIn(s?.seconds_until_next_check)}</p></div>
      </div>

      <div className="bg-gray-900/40 border border-gray-800 rounded-xl p-4 space-y-3">
        <h3 className="text-sm font-semibold text-gray-200">Tracked wallets</h3>
        <div className="space-y-2">
          {(s?.targets ?? []).map((t: any) => {
            const opened = openWallet === t.wallet
            const scopedEvents = (s?.recent_events ?? []).filter((e: any) => String(e?.source_wallet || '') === String(t.wallet))
            return (
              <div key={String(t.wallet)} className="border border-gray-800 rounded-lg bg-gray-900/30">
                <button
                  type="button"
                  onClick={() => setOpenWallet(opened ? null : String(t.wallet))}
                  className="w-full px-3 py-2 text-left text-xs flex items-center justify-between gap-3"
                >
                  <span className="text-gray-200 font-mono truncate">{String(t.wallet)}</span>
                  <span className="flex items-center gap-2">
                    <span className={`text-[10px] px-2 py-0.5 rounded border ${t?.health === 'healthy' ? 'text-emerald-300 border-emerald-700/70 bg-emerald-900/20' : 'text-amber-300 border-amber-700/70 bg-amber-900/20'}`}>
                      {t?.health === 'healthy' ? 'healthy' : 'degraded'}
                    </span>
                    <span className="text-gray-500">{opened ? 'hide' : 'show'}</span>
                  </span>
                </button>
                <div className="px-3 pb-3 grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
                  <div className="bg-gray-900/40 border border-gray-800 rounded-lg p-3"><p className="text-gray-500">Open positions</p><p className="mt-1 text-gray-200">{fmtNum(t?.open_positions_count)}</p><p className="text-[10px] text-gray-500 mt-1">last buy: {fmtAgo(t?.last_buy_age_seconds)} {t?.last_buy_at ? `(${fmtTs(t?.last_buy_at)})` : ''}</p></div>
                  <div className="bg-gray-900/40 border border-gray-800 rounded-lg p-3"><p className="text-gray-500">BUY activity share</p><p className="mt-1 text-gray-200">{typeof t?.recent_buy_share_pct === 'number' ? `${t.recent_buy_share_pct}%` : '—'}</p><p className="text-[10px] text-gray-500 mt-1">{fmtNum(t?.recent_buy_trades_count)} / {fmtNum(t?.recent_activity_count)}</p></div>
                  <div className="bg-gray-900/40 border border-gray-800 rounded-lg p-3"><p className="text-gray-500">Open positions cash PnL</p><p className="mt-1 text-gray-200">{fmtUsdSigned(t?.open_positions_cash_pnl_sum)}</p></div>
                  <div className="bg-gray-900/40 border border-gray-800 rounded-lg p-3"><p className="text-gray-500">Copied / skipped</p><p className="mt-1 text-gray-200">{fmtNum(t?.copied_count)} / {fmtNum(t?.skipped_count)}</p><p className="text-[10px] text-gray-500 mt-1">updated: {fmtTs(t?.updated_at)}</p></div>
                </div>
                <div className="px-3 pb-3 text-[11px] text-gray-400 flex flex-wrap gap-x-3 gap-y-1">
                  <span>last fetch ok: {fmtTs(t?.last_fetch_ok_at)}</span>
                  <span>last fetch error: {t?.last_fetch_error ? String(t.last_fetch_error) : '—'}</span>
                  <span>retry in: {fmtNextIn(t?.next_retry_in_seconds)}</span>
                </div>
                {t?.error ? <p className="px-3 pb-3 text-xs text-amber-400">Stats warning: {String(t.error)}</p> : null}
                {opened ? (
                  <div className="px-3 pb-3">
                    <p className="text-[11px] text-gray-500 mb-1">
                      Skip reasons: {Object.entries((t?.skip_reasons ?? {}) as Record<string, number>).length > 0
                        ? Object.entries((t?.skip_reasons ?? {}) as Record<string, number>)
                            .sort((a, b) => b[1] - a[1])
                            .slice(0, 5)
                            .map(([k, v]) => `${k}(${v})`)
                            .join(', ')
                        : '—'}
                    </p>
                    <p className="text-[11px] text-gray-500 mb-1">Recent events for this wallet</p>
                    <div className="max-h-48 overflow-auto border border-gray-800 rounded-lg">
                      <table className="w-full text-xs">
                        <tbody>
                          {scopedEvents.map((e: any, i: number) => (
                            <tr key={`${e.ts}-${i}`} className="border-t border-gray-800">
                              <td className="px-2 py-1 text-gray-400 font-mono">{String(e.ts || '')}</td>
                              <td className="px-2 py-1 text-gray-300">{String(e.level || '')}</td>
                              <td className="px-2 py-1 text-gray-300">{String(e.message || '')}</td>
                            </tr>
                          ))}
                          {scopedEvents.length === 0 ? (
                            <tr><td className="px-2 py-2 text-gray-500" colSpan={3}>No wallet-scoped events yet.</td></tr>
                          ) : null}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : null}
              </div>
            )
          })}
          {(s?.targets ?? []).length === 0 ? <p className="text-xs text-gray-500">No wallets configured yet.</p> : null}
        </div>
      </div>

      <div className="bg-gray-900/40 border border-gray-800 rounded-xl p-4 space-y-3">
        <h3 className="text-sm font-semibold text-gray-200">Recent worker events</h3>
        <div className="max-h-[420px] overflow-auto border border-gray-800 rounded-lg">
          <table className="w-full text-xs">
            <thead className="bg-gray-900/70">
              <tr>
                <th className="text-left px-2 py-1.5 text-gray-500">Time</th>
                <th className="text-left px-2 py-1.5 text-gray-500">Level</th>
                <th className="text-left px-2 py-1.5 text-gray-500">Message</th>
              </tr>
            </thead>
            <tbody>
              {(s?.recent_events ?? []).map((e: any, i: number) => (
                <tr key={`${e.ts}-${i}`} className="border-t border-gray-800">
                  <td className="px-2 py-1.5 text-gray-400 font-mono">{String(e.ts || '')}</td>
                  <td className="px-2 py-1.5 text-gray-300">{String(e.level || '')}</td>
                  <td className="px-2 py-1.5 text-gray-300">{String(e.message || '')}</td>
                </tr>
              ))}
              {(s?.recent_events ?? []).length === 0 && (
                <tr><td className="px-2 py-2 text-gray-500" colSpan={3}>No events yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

