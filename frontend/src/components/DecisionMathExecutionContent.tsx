import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { fmt, actionBadge } from '../lib/utils'
import type { RunTraceExecutionEvent } from '../api/client'

export type DecisionRow = {
  id: string
  market_id: string
  action: string
  reason?: string | null
  bet_size_usd?: number | null
  kelly_fraction?: number | null
  p_yes?: number | null
  p_market?: number | null
  gap?: number | null
  decision_trace?: Record<string, unknown> | null
}

function severityRowClass(sev: string): string {
  if (sev === 'error' || sev === 'critical') return 'border-l-2 border-l-red/70 bg-red/5'
  if (sev === 'warn') return 'border-l-2 border-l-yellow/70 bg-yellow/5'
  return 'border-l-2 border-l-transparent'
}

function Kv({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex justify-between gap-3 text-xs py-1 border-b border-gray-800/80 last:border-0">
      <span className="text-gray-500 shrink-0">{label}</span>
      <span className="text-gray-200 font-mono text-right break-all">{value}</span>
    </div>
  )
}

function SubPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-800/40 p-3">
      <p className="text-[11px] font-medium uppercase tracking-wide text-gray-500 mb-2">{title}</p>
      <div>{children}</div>
    </div>
  )
}

function SectionTitle({ children }: { children: ReactNode }) {
  return (
    <p className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 border-b border-gray-800 pb-1.5 mb-2">
      {children}
    </p>
  )
}

function CalculationBlock({ trace }: { trace: Record<string, unknown> | null | undefined }) {
  if (!trace || typeof trace !== 'object') {
    return <p className="text-xs text-gray-500">No calculation trace stored for this decision.</p>
  }

  const kelly = trace.kelly as Record<string, unknown> | undefined
  const exchange = trace.exchange as Record<string, unknown> | undefined
  const sizing = trace.sizing as Record<string, unknown> | undefined
  const ev = trace.ev as Record<string, unknown> | undefined
  const hasBlocks = kelly || exchange || sizing || ev

  if (!hasBlocks) {
    return (
      <div className="space-y-1">
        {trace.gap_threshold != null && <Kv label="Gap threshold" value={fmt(Number(trace.gap_threshold), 3)} />}
        {trace.confidence_threshold != null && (
          <Kv label="Confidence threshold" value={fmt(Number(trace.confidence_threshold), 2)} />
        )}
        <p className="text-xs text-gray-500 pt-2">Sizing / Kelly details were not recorded (e.g. early skip).</p>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
      {kelly && (
        <SubPanel title="Kelly">
          {kelly.kelly_divisor != null && <Kv label="Kelly divisor" value={String(kelly.kelly_divisor)} />}
          {kelly.max_bet_fraction != null && <Kv label="Max bet fraction" value={fmt(Number(kelly.max_bet_fraction), 4)} />}
        </SubPanel>
      )}
      {exchange && (
        <SubPanel title="Exchange">
          {exchange.tick_size != null && <Kv label="Tick size" value={String(exchange.tick_size)} />}
          {exchange.min_order_size != null && <Kv label="Min order size" value={String(exchange.min_order_size)} />}
        </SubPanel>
      )}
      {sizing && (
        <SubPanel title="Sizing">
          {sizing.kelly_size != null && <Kv label="Kelly size" value={`$${fmt(Number(sizing.kelly_size), 2)}`} />}
          {sizing.max_stake_cap_usd != null && (
            <Kv label="Max stake cap" value={`$${fmt(Number(sizing.max_stake_cap_usd), 2)}`} />
          )}
          {sizing.target_size != null && <Kv label="Target size (legacy)" value={`$${fmt(Number(sizing.target_size), 2)}`} />}
          {sizing.ideal_size != null && <Kv label="Ideal size" value={`$${fmt(Number(sizing.ideal_size), 2)}`} />}
          {sizing.final_size != null && <Kv label="Final size" value={`$${fmt(Number(sizing.final_size), 2)}`} />}
        </SubPanel>
      )}
      {ev && (
        <SubPanel title="EV after costs">
          {ev.taker_fee_bps != null && <Kv label="Taker fee (bps)" value={String(ev.taker_fee_bps)} />}
          {ev.slippage_tolerance != null && (
            <Kv label="Slippage tolerance" value={fmt(Number(ev.slippage_tolerance), 4)} />
          )}
          {ev.fee_usd_est != null && <Kv label="Fee (est.)" value={`$${fmt(Number(ev.fee_usd_est), 4)}`} />}
          {ev.slippage_usd_est != null && (
            <Kv label="Slippage (est.)" value={`$${fmt(Number(ev.slippage_usd_est), 4)}`} />
          )}
          {ev.ev_after_costs_usd != null && (
            <Kv label="EV after costs" value={`$${fmt(Number(ev.ev_after_costs_usd), 4)}`} />
          )}
        </SubPanel>
      )}
    </div>
  )
}

function DecisionBlock({ d }: { d: DecisionRow }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-800/40 p-3 space-y-1">
      <p className="text-[11px] font-medium uppercase tracking-wide text-gray-500 mb-2">Decision</p>
      <Kv label="Action" value={<span className="uppercase">{d.action}</span>} />
      {d.reason != null && d.reason !== '' && <Kv label="Reason" value={d.reason} />}
      {d.bet_size_usd != null && <Kv label="Bet size" value={`$${fmt(Number(d.bet_size_usd), 2)}`} />}
      {d.kelly_fraction != null && <Kv label="Kelly fraction" value={fmt(Number(d.kelly_fraction), 4)} />}
      {d.p_yes != null && <Kv label="p_yes" value={fmt(Number(d.p_yes), 4)} />}
      {d.p_market != null && <Kv label="p_market" value={fmt(Number(d.p_market), 4)} />}
      {d.gap != null && <Kv label="Gap" value={fmt(Number(d.gap), 4)} />}
    </div>
  )
}

function ExecutionEventRow({ e }: { e: RunTraceExecutionEvent }) {
  const [open, setOpen] = useState(false)
  const payload = e.payload && typeof e.payload === 'object' && Object.keys(e.payload).length > 0
  const ids =
    e.client_order_id || e.exchange_order_id
      ? [e.client_order_id && `client: ${e.client_order_id}`, e.exchange_order_id && `exchange: ${e.exchange_order_id}`]
          .filter(Boolean)
          .join(' · ')
      : null

  return (
    <div className={`rounded-md pl-2 pr-2 py-2 ${severityRowClass(e.severity)}`}>
      <div className="flex flex-wrap items-start gap-x-3 gap-y-1 text-xs">
        <span className="text-gray-500 font-mono whitespace-nowrap shrink-0">{e.event_time ?? '—'}</span>
        <span
          className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${
            e.severity === 'error' || e.severity === 'critical'
              ? 'bg-red/20 text-red'
              : e.severity === 'warn'
                ? 'bg-yellow/15 text-yellow'
                : e.severity === 'debug'
                  ? 'bg-border text-muted'
                  : 'bg-gray-800 text-gray-400'
          }`}
        >
          {e.severity}
        </span>
        <span className="text-gray-300 font-medium">{e.stage}</span>
        <span className="text-gray-400 min-w-0 break-all">{e.event_type}</span>
      </div>
      {ids && <p className="text-[11px] text-gray-500 mt-1 font-mono break-all">{ids}</p>}
      {payload && (
        <div className="mt-1">
          <button type="button" onClick={() => setOpen(o => !o)} className="text-[11px] text-accent hover:underline">
            {open ? 'Hide payload' : 'Payload'}
          </button>
          {open && (
            <pre className="mt-1 text-[10px] leading-relaxed text-gray-400 font-mono whitespace-pre-wrap break-all bg-gray-950/80 rounded p-2 border border-gray-800 max-h-40 overflow-auto">
              {JSON.stringify(e.payload, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}

function LogFilterToggle({
  value,
  onChange,
}: {
  value: 'all' | 'issues'
  onChange: (v: 'all' | 'issues') => void
}) {
  return (
    <div className="inline-flex rounded-md border border-gray-800 overflow-hidden text-[11px]">
      <button
        type="button"
        onClick={() => onChange('all')}
        className={`px-2.5 py-1 transition-colors ${value === 'all' ? 'bg-gray-800 text-gray-200' : 'text-gray-500 hover:text-gray-300'}`}
      >
        All
      </button>
      <button
        type="button"
        onClick={() => onChange('issues')}
        className={`px-2.5 py-1 border-l border-gray-800 transition-colors ${
          value === 'issues' ? 'bg-gray-800 text-gray-200' : 'text-gray-500 hover:text-gray-300'
        }`}
      >
        Issues only
      </button>
    </div>
  )
}

function ExecutionBlock({ events }: { events: RunTraceExecutionEvent[] }) {
  const [filter, setFilter] = useState<'all' | 'issues'>('all')
  const filtered = useMemo(() => {
    if (filter === 'all') return events
    return events.filter(e => e.severity === 'warn' || e.severity === 'error' || e.severity === 'critical')
  }, [events, filter])

  if (events.length === 0) {
    return <p className="text-xs text-gray-500">No execution events for this decision.</p>
  }

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
        <span className="text-[11px] text-gray-500 uppercase tracking-wide">Execution</span>
        <LogFilterToggle value={filter} onChange={setFilter} />
      </div>
      {filtered.length === 0 ? (
        <p className="text-xs text-gray-500">No warn/error/critical events.</p>
      ) : (
        <div className="space-y-1 max-h-72 overflow-y-auto border border-gray-800 rounded-lg p-2 bg-gray-950/30">
          {filtered.map(e => (
            <ExecutionEventRow key={e.id} e={e} />
          ))}
        </div>
      )}
    </div>
  )
}

function decisionStatusMeta(events: RunTraceExecutionEvent[]) {
  const n = events.length
  const issues = events.filter(e => e.severity === 'warn' || e.severity === 'error' || e.severity === 'critical').length
  return { n, issues }
}

export type MarketTraceSection = 'math' | 'execution' | 'all'

function DecisionTraceBody({
  d,
  events,
  section = 'all',
}: {
  d: DecisionRow
  events: RunTraceExecutionEvent[]
  /** `math` = sizing / Kelly / decision / raw JSON; `execution` = order & execution log; `all` = accordion body. */
  section?: MarketTraceSection
}) {
  const trace = d.decision_trace as Record<string, unknown> | null | undefined
  const [rawOpen, setRawOpen] = useState(false)

  if (section === 'execution') {
    return (
      <div className="space-y-5">
        <div>
          <SectionTitle>Order and execution</SectionTitle>
          <ExecutionBlock events={events} />
        </div>
      </div>
    )
  }

  if (section === 'math') {
    return (
      <div className="space-y-5">
        <div>
          <SectionTitle>Calculation</SectionTitle>
          <CalculationBlock trace={trace} />
        </div>
        <div>
          <SectionTitle>Recorded decision</SectionTitle>
          <DecisionBlock d={d} />
        </div>
        <div>
          <button
            type="button"
            onClick={() => setRawOpen(r => !r)}
            className="text-[11px] text-gray-500 hover:text-gray-300"
          >
            {rawOpen ? '▼' : '▶'} Raw decision_trace (JSON)
          </button>
          {rawOpen && (
            <pre className="mt-2 text-[10px] leading-relaxed text-gray-400 font-mono whitespace-pre-wrap break-all bg-gray-950/80 rounded-lg p-3 border border-gray-800 max-h-48 overflow-auto">
              {trace ? JSON.stringify(trace, null, 2) : '—'}
            </pre>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <div>
        <SectionTitle>Calculation</SectionTitle>
        <CalculationBlock trace={trace} />
      </div>
      <div>
        <SectionTitle>Recorded decision</SectionTitle>
        <DecisionBlock d={d} />
      </div>
      <div>
        <SectionTitle>Order and execution</SectionTitle>
        <ExecutionBlock events={events} />
      </div>
      <div>
        <button
          type="button"
          onClick={() => setRawOpen(r => !r)}
          className="text-[11px] text-gray-500 hover:text-gray-300"
        >
          {rawOpen ? '▼' : '▶'} Raw decision_trace (JSON)
        </button>
        {rawOpen && (
          <pre className="mt-2 text-[10px] leading-relaxed text-gray-400 font-mono whitespace-pre-wrap break-all bg-gray-950/80 rounded-lg p-3 border border-gray-800 max-h-48 overflow-auto">
            {trace ? JSON.stringify(trace, null, 2) : '—'}
          </pre>
        )}
      </div>
    </div>
  )
}

function DecisionExecutionAccordion({
  d,
  events,
  marketTitle,
  defaultOpen,
}: {
  d: DecisionRow
  events: RunTraceExecutionEvent[]
  marketTitle: string
  defaultOpen: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  useEffect(() => {
    setOpen(defaultOpen)
  }, [defaultOpen])

  const { n, issues } = decisionStatusMeta(events)

  return (
    <div className="border border-gray-800 rounded-xl overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-800/50 transition-colors text-left"
      >
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <span className="text-xs text-gray-500 shrink-0">{open ? '−' : '+'}</span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium text-gray-200 truncate" title={d.market_id}>
                {marketTitle}
              </span>
              {d.action && (
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium shrink-0 ${actionBadge(d.action)}`}>
                  {d.action}
                </span>
              )}
            </div>
            <p className="text-[11px] text-gray-500 mt-0.5 truncate font-mono" title={d.market_id}>
              {d.market_id}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0 ml-3">
          {d.bet_size_usd != null && Number(d.bet_size_usd) > 0 && (
            <span className="text-xs text-gray-400 hidden sm:inline">
              <strong className="text-white">${fmt(Number(d.bet_size_usd), 2)}</strong>
            </span>
          )}
          {n > 0 && (
            <span className="text-[11px] text-gray-500">
              {n} event{n !== 1 ? 's' : ''}
              {issues > 0 && <span className="text-yellow ml-1">· {issues} issue{issues !== 1 ? 's' : ''}</span>}
            </span>
          )}
          <span className="text-xs text-gray-500">{open ? 'Collapse' : 'Expand'}</span>
        </div>
      </button>
      {open && (
        <div className="border-t border-gray-800 px-4 py-4 space-y-5 bg-gray-900/30">
          <DecisionTraceBody d={d} events={events} />
        </div>
      )}
    </div>
  )
}

function sortByTime(a: RunTraceExecutionEvent, b: RunTraceExecutionEvent) {
  const ta = a.event_time ?? ''
  const tb = b.event_time ?? ''
  if (ta !== tb) return ta.localeCompare(tb)
  return a.id - b.id
}

export function groupEventsByDecision(events: RunTraceExecutionEvent[]): {
  byDecisionId: Map<string, RunTraceExecutionEvent[]>
  orphans: RunTraceExecutionEvent[]
} {
  const byDecisionId = new Map<string, RunTraceExecutionEvent[]>()
  const orphans: RunTraceExecutionEvent[] = []
  for (const e of events) {
    const did = e.decision_id
    if (did) {
      if (!byDecisionId.has(did)) byDecisionId.set(did, [])
      byDecisionId.get(did)!.push(e)
    } else {
      orphans.push(e)
    }
  }
  for (const arr of byDecisionId.values()) arr.sort(sortByTime)
  orphans.sort(sortByTime)
  return { byDecisionId, orphans }
}

export function DecisionMathExecutionContent({
  decisions,
  execution_events,
  execution_events_total,
  marketTitleById,
  defaultOpen = false,
  filterMarketId,
  filterSection,
}: {
  decisions: DecisionRow[]
  execution_events: RunTraceExecutionEvent[]
  execution_events_total: number
  marketTitleById: Record<string, string>
  /** Used for the full-run accordion list (ignored when filterMarketId is set). */
  defaultOpen?: boolean
  /** When set, only decisions (and linked execution events) for this market are shown — flat layout, no accordions. */
  filterMarketId?: string | null
  /** When filtering by market: show only math (calc + decision + raw) or only execution, or the full single scroll (`all`). */
  filterSection?: MarketTraceSection
}) {
  const sectionFlat: MarketTraceSection = filterSection ?? 'all'

  const { decisionsScoped, eventsScoped } = useMemo(() => {
    if (!filterMarketId) {
      return { decisionsScoped: decisions, eventsScoped: execution_events }
    }
    const drows = decisions.filter(d => d.market_id === filterMarketId)
    const idSet = new Set(drows.map(d => d.id))
    const ev = execution_events.filter(e => e.decision_id && idSet.has(e.decision_id))
    return { decisionsScoped: drows, eventsScoped: ev }
  }, [decisions, execution_events, filterMarketId])

  const { byDecisionId, orphans } = useMemo(() => groupEventsByDecision(eventsScoped), [eventsScoped])
  const truncated = execution_events_total > execution_events.length

  const showExecutionTruncationHint = truncated && sectionFlat !== 'math'

  return (
    <div className="space-y-3">
      {showExecutionTruncationHint && (
        <p className="text-xs text-yellow/90 bg-yellow/5 border border-yellow/20 rounded-lg px-3 py-2">
          Showing the first {execution_events.length} of {execution_events_total} execution events for this run. Older
          events are omitted here; use the trace API with offset if you need the full append-only log.
        </p>
      )}
      {decisionsScoped.length === 0 ? (
        <p className="text-gray-500 text-sm">
          {filterMarketId ? 'No decision rows for this market.' : 'No decision rows for this run.'}
        </p>
      ) : filterMarketId ? (
        <div className="space-y-8">
          {decisionsScoped.map((d, i) => (
            <div key={d.id}>
              {i > 0 && <div className="border-t border-gray-800" role="separator" />}
              {decisionsScoped.length > 1 && (
                <p className={`text-[11px] text-gray-500 font-mono ${i > 0 ? 'mt-8 mb-4' : 'mb-4'}`}>{d.id}</p>
              )}
              <DecisionTraceBody
                d={d}
                events={byDecisionId.get(d.id) ?? []}
                section={sectionFlat}
              />
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {decisionsScoped.map(d => (
            <DecisionExecutionAccordion
              key={d.id}
              d={d}
              events={byDecisionId.get(d.id) ?? []}
              marketTitle={marketTitleById[d.market_id] || d.market_id}
              defaultOpen={defaultOpen}
            />
          ))}
        </div>
      )}
      {!filterMarketId && orphans.length > 0 && (
        <div className="border border-gray-800 border-dashed rounded-xl overflow-hidden bg-gray-900/20">
          <p className="text-xs text-gray-500 px-4 py-3 border-b border-gray-800">
            Other events (no decision link){' '}
            <span className="text-gray-400">· {orphans.length} event{orphans.length !== 1 ? 's' : ''}</span>
          </p>
          <div className="px-4 py-3">
            <ExecutionBlock events={orphans} />
          </div>
        </div>
      )}
    </div>
  )
}
