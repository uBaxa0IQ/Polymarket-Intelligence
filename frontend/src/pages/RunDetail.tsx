import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  fetchRun,
  fetchRunAnalyses,
  fetchRunLLMCalls,
  fetchRunRanker,
  fetchRunScreener,
  fetchRunTrace,
} from '../api/client'
import { fmtDate, statusColor } from '../lib/utils'
import { useEffect, useState, type ReactNode } from 'react'
import { RunAnalyzedMarketsSection } from '../components/RunAnalyzedMarketsSection'
import type { DecisionRow } from '../components/DecisionMathExecutionContent'
import { ErrorState, LoadingState } from '../components/QueryStates'

function StageAccordion({
  title,
  subtitle,
  defaultOpen,
  children,
}: {
  title: string
  subtitle?: string
  defaultOpen?: boolean
  children: ReactNode
}) {
  const [open, setOpen] = useState(!!defaultOpen)
  useEffect(() => {
    setOpen(!!defaultOpen)
  }, [defaultOpen])
  return (
    <div className="border border-gray-800 rounded-xl overflow-hidden bg-gray-900/40">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-800/50 text-left"
      >
        <div>
          <h3 className="text-sm font-semibold text-gray-200">{title}</h3>
          {subtitle && <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>}
        </div>
        <span className="text-xs text-gray-500">{open ? 'Collapse' : 'Expand'}</span>
      </button>
      {open && <div className="border-t border-gray-800 px-4 py-3">{children}</div>}
    </div>
  )
}

export default function RunDetail() {
  const { id } = useParams<{ id: string }>()
  const [expandAll, setExpandAll] = useState(false)
  const { data: run, isLoading, isError, refetch } = useQuery({
    queryKey: ['run', id],
    queryFn: () => fetchRun(id!),
    refetchInterval: 5_000,
  })
  const { data: llmCalls = [], isError: llmError } = useQuery({ queryKey: ['run-llm', id], queryFn: () => fetchRunLLMCalls(id!) })
  const { data: screenerData = {}, isError: screenerError } = useQuery({ queryKey: ['run-screener', id], queryFn: () => fetchRunScreener(id!), enabled: !!id })
  const { data: rankerData = {}, isError: rankerError } = useQuery({ queryKey: ['run-ranker', id], queryFn: () => fetchRunRanker(id!), enabled: !!id })
  const { data: analysisSummaries = [] } = useQuery({
    queryKey: ['run-analyses', id],
    queryFn: () => fetchRunAnalyses(id!),
    enabled: !!id,
    refetchInterval: 5_000,
  })
  const traceFetchLimit = 5000
  const { data: traceData, isError: traceError, isPending: tracePending } = useQuery({
    queryKey: ['run-trace', id, traceFetchLimit],
    queryFn: () =>
      fetchRunTrace(id!, {
        events_limit: traceFetchLimit,
        events_offset: 0,
      }),
    enabled: !!id,
  })

  const runTrace = traceData
    ? {
        decisions: traceData.decisions ?? [],
        execution_events: traceData.execution_events ?? [],
        execution_events_total: traceData.execution_events_total ?? 0,
      }
    : undefined

  const rankerMarkets = Array.isArray((rankerData as any)?.markets) ? (rankerData as any).markets : []
  const rankerParsed = rankerMarkets
  const priorityCounts = rankerParsed.reduce(
    (acc: { high: number; medium: number; low: number; other: number }, item: any) => {
      const p = String(item?.research_priority ?? '')
        .trim()
        .toLowerCase()
      if (p === 'high') acc.high += 1
      else if (p === 'medium') acc.medium += 1
      else if (p === 'low') acc.low += 1
      else acc.other += 1
      return acc
    },
    { high: 0, medium: 0, low: 0, other: 0 },
  )
  const rankedTotal = Number((rankerData as any)?.total_ranked ?? rankerMarkets.length) || null
  const selectedForStage2 = Number((rankerData as any)?.total_selected ?? run?.markets_analyzed ?? 0)
  const screenerMarkets = Array.isArray((screenerData as any)?.markets) ? (screenerData as any).markets : []
  const totalFetched = Number((screenerData as any)?.total_fetched ?? run?.markets_screened ?? screenerMarkets.length) || 0
  const screenerPassed = screenerMarkets.filter((m: any) => !!m?.passed).length
  const screenerFiltered = screenerMarkets.length - screenerPassed
  const screenerReasonCounts = screenerMarkets.reduce(
    (acc: Record<string, number>, item: any) => {
      if (item?.passed) return acc
      const reason = String(item?.filter_reason || 'unknown')
      acc[reason] = (acc[reason] || 0) + 1
      return acc
    },
    {} as Record<string, number>,
  )
  const reasonBreakdown: Array<{ reason: string; count: number; share: number }> = (Object.entries(
    screenerReasonCounts,
  ) as Array<[string, number]>)
    .map(([reason, count]) => ({
      reason,
      count,
      share: screenerFiltered > 0 ? (count / screenerFiltered) * 100 : 0,
    }))
    .sort((a, b) => b.count - a.count)
  const selectionPolicy = String(
    (run?.config_snapshot as { ranker?: { selection_policy?: string } } | null)?.ranker?.selection_policy ??
      'top_n',
  )

  if (isLoading) return <LoadingState label="Loading run details..." />
  if (isError) return <ErrorState message="Failed to load run details." onRetry={() => refetch()} />
  if (!run) return <ErrorState message="Run not found." />

  const llmMarketIds = [...new Set((llmCalls as any[]).filter((c: any) => c.market_id).map((c: any) => c.market_id))]
  const seen = new Set(analysisSummaries.map((s: any) => s.market_id))
  const llmOnlyRows = llmMarketIds
    .filter(mid => !seen.has(mid))
    .map(market_id => ({
      market_id,
      question: null as string | null,
      p_yes: null as number | null,
      p_market: null as number | null,
      gap: null as number | null,
      confidence: null as number | null,
      action: null as string | null,
    }))
  const marketsForAccordion = [...analysisSummaries, ...llmOnlyRows]

  const stageTimeline = [
    { key: 'screener', label: 'Screener', done: totalFetched > 0, value: totalFetched },
    { key: 'ranker', label: 'Ranker', done: rankedTotal != null && rankedTotal > 0, value: rankedTotal ?? '—' },
    { key: 'analysis', label: 'Analysis', done: marketsForAccordion.length > 0, value: marketsForAccordion.length },
    { key: 'decisions', label: 'Decisions', done: (run.decisions_count ?? 0) > 0, value: run.decisions_count ?? '—' },
    { key: 'bets', label: 'Bets', done: (run.bets_placed ?? 0) > 0, value: run.bets_placed ?? '—' },
  ]

  return (
    <div className="space-y-6">
      <div className="sticky top-0 z-20 rounded border border-border bg-base/95 p-3 backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <Link to="/pipeline" className="text-sm text-muted hover:text-white">
              Back to Pipeline
            </Link>
            <span className={`text-sm font-medium ${statusColor(run.status)}`}>{run.status}</span>
            <span className="text-xs text-muted">
              Current stage: {run.current_stage ?? '—'}
            </span>
          </div>
          <button
            type="button"
            onClick={() => setExpandAll(v => !v)}
            className="rounded border border-border px-3 py-1 text-xs text-muted hover:text-white"
          >
            {expandAll ? 'Collapse all' : 'Expand all'}
          </button>
        </div>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <Link to="/pipeline" className="text-gray-500 hover:text-gray-300 text-sm">
          ← Pipeline
        </Link>
        <h2 className="text-xl font-bold">Run</h2>
        <span className={`text-sm font-medium ${statusColor(run.status)}`}>{run.status}</span>
      </div>

      <div className="bg-panel border border-border rounded p-4">
        <p className="text-sm font-medium text-white mb-3">Pipeline timeline</p>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          {stageTimeline.map(s => (
            <div
              key={s.key}
              className={`rounded border px-3 py-2 ${s.done ? 'border-green/40 bg-green/10' : 'border-border bg-card'}`}
            >
              <p className="text-xs text-muted">{s.label}</p>
              <p className="text-sm text-white font-mono mt-1">{s.value}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { l: 'Trigger', v: run.trigger },
          { l: 'Started', v: fmtDate(run.started_at) },
          { l: 'Finished', v: fmtDate(run.finished_at) },
          { l: 'Screened', v: run.markets_screened },
          { l: 'Ranked', v: run.markets_ranked },
          { l: 'Analyzed', v: run.markets_analyzed },
          { l: 'Decisions', v: run.decisions_count },
          { l: 'Bets', v: run.bets_placed },
        ].map(({ l, v }) => (
          <div key={l} className="bg-gray-900 border border-gray-800 rounded-xl p-3">
            <p className="text-xs text-gray-500">{l}</p>
            <p className="text-sm font-medium text-gray-200 mt-0.5">{v ?? '—'}</p>
          </div>
        ))}
      </div>

      {run.error_message && (
        <div className="bg-red-950 border border-red-900 rounded-xl p-4 text-sm text-red-300">
          <strong>Error:</strong> {run.error_message}
        </div>
      )}
      {(screenerError || rankerError || llmError) && (
        <ErrorState message="Some run sections failed to load. Data shown may be partial." />
      )}

      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider">Pipeline stages</h3>

        <StageAccordion
          title="Screening"
          defaultOpen={expandAll}
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="bg-gray-800/60 border border-gray-800 rounded-lg p-3">
              <p className="text-xs text-gray-500">Screened</p>
              <p className="text-sm text-gray-200 mt-1">
                <strong className="text-white">{totalFetched || '—'}</strong>
              </p>
            </div>
            <div className="bg-gray-800/60 border border-gray-800 rounded-lg p-3">
              <p className="text-xs text-gray-500">Passed screener</p>
              <p className="text-sm text-gray-200 mt-1">
                <strong className="text-white">{screenerPassed}</strong>
              </p>
            </div>
            <div className="bg-gray-800/60 border border-gray-800 rounded-lg p-3">
              <p className="text-xs text-gray-500">Filtered at screener</p>
              <p className="text-sm text-gray-200 mt-1">
                <strong className="text-white">{screenerFiltered}</strong>
              </p>
            </div>
            <div className="bg-gray-800/60 border border-gray-800 rounded-lg p-3">
              <p className="text-xs text-gray-500">Selected for Stage 2</p>
              <p className="text-sm text-gray-200 mt-1">
                <strong className="text-white">{selectedForStage2 ?? '—'}</strong>
              </p>
            </div>
            <div className="bg-gray-800/60 border border-gray-800 rounded-lg p-3 md:col-span-2">
              <p className="text-xs text-gray-500">Ranker priorities</p>
              <p className="text-sm text-gray-200 mt-1">
                high <strong className="text-white">{priorityCounts.high}</strong>
                {' / '}
                medium <strong className="text-white">{priorityCounts.medium}</strong>
                {' / '}
                low <strong className="text-white">{priorityCounts.low}</strong>
                {priorityCounts.other > 0 && (
                  <>
                    {' / '}
                    other <strong className="text-white">{priorityCounts.other}</strong>
                  </>
                )}
              </p>
              <p className="text-xs text-gray-500 mt-1">
                Ranked total: {rankedTotal ?? '—'} · Selection policy: {selectionPolicy}
              </p>
            </div>
          </div>
          {reasonBreakdown.length > 0 && (
            <div className="mt-3 overflow-auto border border-gray-800 rounded-lg">
              <table className="w-full text-xs">
                <thead className="bg-gray-900/70">
                  <tr>
                    <th className="text-left px-2 py-1.5 text-gray-500">Filter reason</th>
                    <th className="text-right px-2 py-1.5 text-gray-500">Count</th>
                    <th className="text-right px-2 py-1.5 text-gray-500">Share</th>
                  </tr>
                </thead>
                <tbody>
                  {reasonBreakdown.map(row => (
                    <tr key={row.reason} className="border-t border-gray-800">
                      <td className="px-2 py-1.5 text-gray-300">{row.reason}</td>
                      <td className="px-2 py-1.5 text-right text-gray-200 font-mono">{row.count}</td>
                      <td className="px-2 py-1.5 text-right text-gray-400 font-mono">{row.share.toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </StageAccordion>

        <StageAccordion title="Ranking (ranker)" defaultOpen={expandAll}>
          {rankerParsed.length === 0 ? (
            <p className="text-gray-500 text-sm">No recorded ranker results for this run.</p>
          ) : (
            <div className="overflow-auto border border-gray-800 rounded-lg">
              <table className="w-full text-xs">
                <thead className="bg-gray-900/70">
                  <tr>
                    <th className="text-left px-2 py-1.5 text-gray-500">Market</th>
                    <th className="text-left px-2 py-1.5 text-gray-500">Priority</th>
                    <th className="text-left px-2 py-1.5 text-gray-500">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {rankerParsed.map((m: any) => (
                    <tr key={m.id} className="border-t border-gray-800">
                      <td className="px-2 py-1.5 text-gray-200 truncate max-w-[26rem]" title={m.question}>{m.question || m.id}</td>
                      <td className="px-2 py-1.5 text-gray-300">{String(m.research_priority || 'unknown').toUpperCase()}</td>
                      <td className="px-2 py-1.5 text-gray-400">{m.structural_reason || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </StageAccordion>

        <StageAccordion title="Analyzed markets" defaultOpen={expandAll}>
          <RunAnalyzedMarketsSection
            runId={id!}
            markets={marketsForAccordion as any[]}
            decisions={(runTrace?.decisions ?? []) as DecisionRow[]}
            execution_events={runTrace?.execution_events ?? []}
            execution_events_total={runTrace?.execution_events_total ?? 0}
            traceError={traceError}
            tracePending={tracePending}
            runTracePresent={!!runTrace}
          />
        </StageAccordion>
      </div>
    </div>
  )
}
