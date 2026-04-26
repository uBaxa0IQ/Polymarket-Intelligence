import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { fetchRunMarketDetail, type RunTraceExecutionEvent } from '../api/client'
import DebateViewer, { isSimplePipeline, type DebateViewerAnalysisTab } from './DebateViewer'
import { DecisionMathExecutionContent, type DecisionRow } from './DecisionMathExecutionContent'
import { fmt, actionBadge, gapColor } from '../lib/utils'

export type AnalyzedMarketRow = {
  market_id: string
  question?: string | null
  p_yes?: number | null
  p_market?: number | null
  gap?: number | null
  action?: string | null
  debate_pairs_completed?: number | null
  debate_consensus?: boolean | null
  debate_stop_reason?: string | null
}

type WorkspaceTab = 'primary' | 'secondary' | 'llm' | 'math' | 'execution'

export function RunAnalyzedMarketsSection({
  runId,
  markets,
  decisions,
  execution_events,
  execution_events_total,
  traceError,
  tracePending,
  runTracePresent,
}: {
  runId: string
  markets: AnalyzedMarketRow[]
  decisions: DecisionRow[]
  execution_events: RunTraceExecutionEvent[]
  execution_events_total: number
  traceError: boolean
  tracePending: boolean
  runTracePresent: boolean
}) {
  const [selectedMarketId, setSelectedMarketId] = useState<string | null>(null)
  const [workspaceTab, setWorkspaceTab] = useState<WorkspaceTab>('primary')

  const idsKey = markets.map(m => m.market_id).join('|')
  useEffect(() => {
    if (markets.length === 0) {
      setSelectedMarketId(null)
      return
    }
    setSelectedMarketId(prev => {
      if (prev && markets.some(m => m.market_id === prev)) return prev
      return markets[0].market_id
    })
  }, [runId, idsKey, markets])

  useEffect(() => {
    setWorkspaceTab('primary')
  }, [selectedMarketId])

  const marketTitleById = useMemo(
    () => Object.fromEntries(markets.map(ma => [ma.market_id, ma.question || ma.market_id])),
    [markets],
  )

  const { data: marketDetail, isPending: marketPending, isError: marketError } = useQuery({
    queryKey: ['run-market', runId, selectedMarketId],
    queryFn: () => fetchRunMarketDetail(runId, selectedMarketId!),
    enabled: !!selectedMarketId,
  })

  const simple = useMemo(() => isSimplePipeline(marketDetail?.llm_calls), [marketDetail?.llm_calls])
  const analysisTab: DebateViewerAnalysisTab = useMemo(() => {
    if (workspaceTab === 'llm') return 'llm'
    if (simple) {
      if (workspaceTab === 'primary') return 'simple_summary'
      if (workspaceTab === 'secondary') return 'simple_output'
    } else {
      if (workspaceTab === 'primary') return 'evidence'
      if (workspaceTab === 'secondary') return 'debate'
    }
    return 'evidence'
  }, [simple, workspaceTab])

  if (markets.length === 0) {
    return <p className="text-gray-500 text-sm">No analyzed markets.</p>
  }

  const tabBtn = (id: WorkspaceTab, label: string) => (
    <button
      key={id}
      type="button"
      onClick={() => setWorkspaceTab(id)}
      className={`text-xs px-3 py-1.5 rounded-full transition-colors ${
        workspaceTab === id ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'
      }`}
    >
      {label}
    </button>
  )

  const primaryLabel = simple ? 'Summary' : 'Evidence'
  const secondaryLabel = simple ? 'Model output' : 'Debate'
  const llmLabel = simple ? 'LLM calls' : 'LLM Calls'

  return (
    <div className="grid grid-cols-1 lg:grid-cols-[minmax(220px,300px)_1fr] gap-4">
      <div className="rounded-xl border border-gray-800 overflow-hidden bg-gray-900/30 flex flex-col max-h-[min(70vh,28rem)] lg:max-h-[min(80vh,32rem)]">
        <p className="text-[11px] uppercase tracking-wide text-gray-500 px-3 py-2 border-b border-gray-800 shrink-0">
          Markets ({markets.length})
        </p>
        <div className="overflow-y-auto min-h-0 divide-y divide-gray-800">
          {markets.map(ma => {
            const active = ma.market_id === selectedMarketId
            return (
              <button
                key={ma.market_id}
                type="button"
                onClick={() => setSelectedMarketId(ma.market_id)}
                className={`w-full text-left px-3 py-2.5 transition-colors ${
                  active ? 'bg-indigo-950/40 border-l-2 border-l-indigo-500' : 'hover:bg-gray-800/40 border-l-2 border-l-transparent'
                }`}
              >
                <p className="text-sm font-medium text-gray-200 truncate" title={ma.market_id}>
                  {ma.question || ma.market_id}
                </p>
                <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 mt-1 text-[11px] text-gray-500">
                  {ma.action && (
                    <span className={`px-1.5 py-0 rounded font-medium ${actionBadge(ma.action)}`}>{ma.action}</span>
                  )}
                  {ma.p_yes != null && <span>p_yes {fmt(ma.p_yes, 2)}</span>}
                  {ma.p_market != null && <span>p_mkt {fmt(ma.p_market, 2)}</span>}
                  {ma.gap != null && <span className={gapColor(ma.gap)}>gap {fmt(ma.gap, 3)}</span>}
                </div>
              </button>
            )
          })}
        </div>
      </div>

      <div className="rounded-xl border border-gray-800 overflow-hidden bg-gray-900/30 flex flex-col min-h-[min(70vh,24rem)]">
        {!selectedMarketId ? (
          <p className="text-gray-500 text-sm p-4">Select a market.</p>
        ) : (
          <>
            <div className="flex flex-wrap gap-2 px-3 py-2 border-b border-gray-800 shrink-0 items-center">
              {marketError ? (
                <span className="text-xs text-red-400">Could not load market detail.</span>
              ) : (
                <>
                  {!marketDetail && marketPending ? (
                    <span className="text-xs text-gray-500">Loading analysis…</span>
                  ) : (
                    <>
                      {tabBtn('primary', primaryLabel)}
                      {tabBtn('secondary', secondaryLabel)}
                      {tabBtn('llm', llmLabel)}
                    </>
                  )}
                  {tabBtn('math', 'Math')}
                  {tabBtn('execution', 'Execution')}
                </>
              )}
            </div>
            <div className="flex-1 min-h-0 overflow-y-auto">
              {workspaceTab === 'math' || workspaceTab === 'execution' ? (
                <div className="p-3">
                  {traceError ? (
                    <p className="text-gray-500 text-sm">Could not load decision trace.</p>
                  ) : tracePending && !runTracePresent ? (
                    <p className="text-gray-500 text-sm">Loading trace…</p>
                  ) : (
                    <DecisionMathExecutionContent
                      decisions={decisions}
                      execution_events={execution_events}
                      execution_events_total={execution_events_total}
                      marketTitleById={marketTitleById}
                      filterMarketId={selectedMarketId}
                      filterSection={workspaceTab === 'math' ? 'math' : 'execution'}
                    />
                  )}
                </div>
              ) : marketPending && !marketDetail ? (
                <p className="text-gray-500 text-sm p-4">Loading…</p>
              ) : marketError ? (
                <p className="text-gray-500 text-sm p-4">Failed to load this market.</p>
              ) : (
                <DebateViewer
                  runId={runId}
                  marketId={selectedMarketId}
                  activeAnalysisTab={analysisTab}
                  hideTabBar
                  embedded
                />
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
