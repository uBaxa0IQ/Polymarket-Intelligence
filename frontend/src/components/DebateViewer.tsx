import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { fetchRunMarketDetail } from '../api/client'
import { fmt, pct, gapColor } from '../lib/utils'

const DEBATE_MODERN = /^debate_(bull|bear)_(\d+)$/

function debateStageTitle(stage: string): string {
  const m = stage.match(DEBATE_MODERN)
  if (!m) return stage.replace('_', ' R').toUpperCase()
  const side = m[1] === 'bull' ? 'Bull' : 'Bear'
  return `${side} R${m[2]}`
}

export function isSimplePipeline(llm_calls: any[] | undefined): boolean {
  return (llm_calls ?? []).some(c => c.stage === 'simple_agent')
}

function getDebateEntries(llm_calls: any[] | undefined): { key: string; title: string; body: string }[] {
  const calls = llm_calls ?? []
  const modern = calls.filter(c => DEBATE_MODERN.test(c.stage))
  if (modern.length > 0) {
    return [...modern]
      .sort((a, b) => {
        const ma = a.stage.match(DEBATE_MODERN)!
        const mb = b.stage.match(DEBATE_MODERN)!
        const ra = parseInt(ma[2], 10)
        const rb = parseInt(mb[2], 10)
        if (ra !== rb) return ra - rb
        return ma[1] === 'bull' ? -1 : 1
      })
      .map(c => ({
        key: c.stage,
        title: debateStageTitle(c.stage),
        body: (c.response_raw as string) ?? '—',
      }))
  }
  const debateMap: Record<string, string> = {}
  for (const c of calls) {
    debateMap[c.stage] = c.response_raw
  }
  const legacyStages = ['bull_r1', 'bear_r1', 'bull_r2', 'bear_r2']
  return legacyStages.map(stage => ({
    key: stage,
    title: stage.replace('_', ' R').toUpperCase(),
    body: debateMap[stage] ?? '—',
  }))
}

type TabFull = 'evidence' | 'debate' | 'llm'
type TabSimple = 'simple_summary' | 'simple_output' | 'llm'
export type DebateViewerAnalysisTab = TabFull | TabSimple

export default function DebateViewer({
  runId,
  marketId,
  activeAnalysisTab,
  hideTabBar = false,
  embedded = false,
}: {
  runId: string
  marketId: string
  /** Controlled analysis tab (hideTabBar + parent tab strip). */
  activeAnalysisTab?: DebateViewerAnalysisTab
  hideTabBar?: boolean
  /** Omit top border / margin when nested in a parent card. */
  embedded?: boolean
}) {
  const { data, isLoading } = useQuery({
    queryKey: ['run-market', runId, marketId],
    queryFn: () => fetchRunMarketDetail(runId, marketId),
  })
  const [tab, setTab] = useState<DebateViewerAnalysisTab>('evidence')

  const simple = useMemo(() => isSimplePipeline(data?.llm_calls), [data?.llm_calls])
  const debateEntries = useMemo(() => getDebateEntries(data?.llm_calls), [data?.llm_calls])

  /** Maps legacy default tab to simple tabs before first user click. */
  const tabForRender = useMemo((): DebateViewerAnalysisTab => {
    if (!data) return 'evidence'
    const raw = activeAnalysisTab !== undefined ? activeAnalysisTab : tab
    if (simple) {
      if (raw === 'simple_summary' || raw === 'simple_output' || raw === 'llm') return raw
      return 'simple_summary'
    }
    if (raw === 'evidence' || raw === 'debate' || raw === 'llm') return raw
    return 'evidence'
  }, [data, simple, tab, activeAnalysisTab])

  const simpleAgentCall = useMemo(
    () => (data?.llm_calls ?? []).find((c: any) => c.stage === 'simple_agent'),
    [data?.llm_calls],
  )

  if (isLoading) return <p className="text-gray-500 text-xs p-4">Loading…</p>
  if (!data) return null

  const { analysis, llm_calls } = data

  const debateMap: Record<string, string> = {}
  for (const c of llm_calls ?? []) {
    debateMap[c.stage] = c.response_raw
  }

  const hasDebateStats = analysis.debate_pairs_completed != null

  const rawSimpleOutput =
    (simpleAgentCall?.response_raw as string | undefined) ||
    (Array.isArray(analysis.evidence_pool) && analysis.evidence_pool.length
      ? String((analysis.evidence_pool as string[])[0])
      : '') ||
    '—'

  const outerClass = embedded ? '' : 'border-t border-gray-800 mt-2'

  if (simple) {
    return (
      <div className={outerClass}>
        {!hideTabBar && (
          <div className="flex flex-wrap gap-2 px-4 pt-3 pb-2 border-b border-gray-800">
            {(
              [
                { id: 'simple_summary' as const, label: 'Summary' },
                { id: 'simple_output' as const, label: 'Model output' },
                { id: 'llm' as const, label: 'LLM calls' },
              ] as const
            ).map(({ id, label }) => (
              <button
                key={id}
                type="button"
                onClick={() => setTab(id)}
                className={`text-xs px-3 py-1 rounded-full transition-colors ${
                  tabForRender === id ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        )}

        <div className={hideTabBar ? 'p-4 pt-2' : 'p-4'}>
          {tabForRender === 'simple_summary' && (
            <div className="space-y-3 max-h-96 overflow-y-auto">
              <div className="flex flex-wrap gap-3 text-xs text-gray-200">
                <span>
                  p_yes: <strong className="text-white">{pct(analysis.p_yes)}</strong>
                </span>
                <span>
                  p_mkt: <strong className="text-white">{pct(analysis.p_market)}</strong>
                </span>
                <span className={gapColor(analysis.gap)}>
                  gap: <strong>{fmt(analysis.gap, 3)}</strong>
                </span>
                <span>
                  confidence: <strong className="text-white">{pct(analysis.confidence)}</strong>
                </span>
              </div>
              {analysis.reasoning ? (
                <div className="rounded-lg border border-gray-800 bg-gray-900/50 p-3">
                  <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">Reasoning</p>
                  <p className="text-xs text-gray-300 whitespace-pre-wrap">{analysis.reasoning}</p>
                </div>
              ) : (
                <p className="text-gray-500 text-xs">No reasoning stored for this analysis.</p>
              )}
              {analysis.failed_stages && (analysis.failed_stages as unknown[]).length > 0 && (
                <div className="rounded border border-amber-900/60 bg-amber-950/30 p-2 text-xs text-amber-200">
                  Failed stages: <span className="font-mono">{JSON.stringify(analysis.failed_stages)}</span>
                </div>
              )}
            </div>
          )}

          {tabForRender === 'simple_output' && (
            <div className="max-h-96 overflow-y-auto">
              <pre className="whitespace-pre-wrap text-xs text-gray-300 font-sans bg-gray-900/60 border border-gray-800 rounded-lg p-3">
                {rawSimpleOutput}
              </pre>
            </div>
          )}

          {tabForRender === 'llm' && (
            <div className="space-y-3 max-h-96 overflow-y-auto">
              {(llm_calls ?? []).map((c: any, i: number) => (
                <div key={i} className="bg-gray-800 rounded-lg p-3 text-xs space-y-2">
                  <div className="flex justify-between gap-2">
                    <span className="font-mono text-indigo-300 shrink-0">{c.stage}</span>
                    <span className="text-gray-500 shrink-0">
                      {fmt(c.duration_seconds)}s{c.error ? ' ❌' : ''}
                    </span>
                  </div>
                  {c.error && <p className="text-red-400">{c.error}</p>}
                  {c.user_prompt && (
                    <div>
                      <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">User prompt</p>
                      <pre className="whitespace-pre-wrap text-gray-400 font-sans bg-gray-900/80 rounded p-2 max-h-40 overflow-y-auto">
                        {c.user_prompt}
                      </pre>
                    </div>
                  )}
                  {c.response_raw && (
                    <div>
                      <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">Response</p>
                      <pre className="whitespace-pre-wrap text-gray-300 font-sans bg-gray-900/80 rounded p-2 max-h-48 overflow-y-auto">
                        {c.response_raw}
                      </pre>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className={outerClass}>
      {!hideTabBar && (
        <div className="flex gap-2 px-4 pt-3 pb-2 border-b border-gray-800">
          {(['evidence', 'debate', 'llm'] as const).map(t => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={`text-xs px-3 py-1 rounded-full transition-colors ${
                tabForRender === t ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'
              }`}
            >
              {t === 'llm' ? 'LLM Calls' : t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
      )}

      <div className={hideTabBar ? 'p-4 pt-2' : 'p-4'}>
        {tabForRender === 'evidence' && (
          <div className="space-y-1 max-h-64 overflow-y-auto">
            {(analysis.evidence_pool ?? []).length === 0 ? (
              <p className="text-gray-500 text-xs">No evidence.</p>
            ) : (
              (analysis.evidence_pool as string[]).map((e, i) => (
                <p key={i} className="text-xs text-gray-300 font-mono bg-gray-800 rounded p-2">
                  {e}
                </p>
              ))
            )}
          </div>
        )}

        {tabForRender === 'debate' && (
          <div className="space-y-3 max-h-96 overflow-y-auto">
            {hasDebateStats && (
              <div className="flex flex-wrap gap-2 text-xs">
                <span className="px-2 py-1 rounded-full bg-gray-800 text-gray-200 border border-gray-700">
                  Pairs: <strong className="text-white">{analysis.debate_pairs_completed}</strong>
                </span>
                {analysis.debate_consensus === true && (
                  <span className="px-2 py-1 rounded-full bg-emerald-950 text-emerald-200 border border-emerald-900">
                    Consensus
                  </span>
                )}
                {analysis.debate_stop_reason && (
                  <span className="px-2 py-1 rounded-full bg-gray-800 text-gray-300 border border-gray-700">
                    Stop: <strong className="text-white">{analysis.debate_stop_reason}</strong>
                  </span>
                )}
              </div>
            )}
            <div className="grid grid-cols-2 gap-4">
              {debateEntries.map(({ key, title, body }) => (
                <div
                  key={key}
                  className={`rounded-lg p-3 text-xs ${
                    key.includes('bull')
                      ? 'bg-green-950 border border-green-900'
                      : 'bg-red-950 border border-red-900'
                  }`}
                >
                  <p className="font-bold mb-2 text-xs uppercase tracking-wider text-gray-400">{title}</p>
                  <pre className="whitespace-pre-wrap text-gray-300 font-sans">{body}</pre>
                </div>
              ))}
            </div>
            {debateMap['judge'] && (
              <div className="bg-indigo-950 border border-indigo-900 rounded-lg p-3">
                <p className="font-bold mb-2 text-xs uppercase tracking-wider text-gray-400">JUDGE VERDICT</p>
                <div className="flex gap-6 text-xs text-gray-200 mb-2 flex-wrap">
                  <span>
                    p_yes: <strong className="text-white">{pct(analysis.p_yes)}</strong>
                  </span>
                  <span>
                    confidence: <strong className="text-white">{pct(analysis.confidence)}</strong>
                  </span>
                  <span>
                    gap: <strong className={gapColor(analysis.gap)}>{fmt(analysis.gap, 3)}</strong>
                  </span>
                </div>
                <p className="text-xs text-gray-300">{analysis.reasoning}</p>
              </div>
            )}
          </div>
        )}

        {tabForRender === 'llm' && (
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {(llm_calls ?? []).map((c: any, i: number) => (
              <div key={i} className="bg-gray-800 rounded-lg p-3 text-xs">
                <div className="flex justify-between mb-1">
                  <span className="font-mono text-indigo-300">{c.stage}</span>
                  <span className="text-gray-500">
                    {fmt(c.duration_seconds)}s{c.error ? ' ❌' : ''}
                  </span>
                </div>
                {c.error && <p className="text-red-400">{c.error}</p>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
