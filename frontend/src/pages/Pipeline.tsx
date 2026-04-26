import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useEffect, useMemo, useState } from 'react'
import {
  fetchRuns, fetchActiveRun, fetchScheduler,
  triggerRun, cancelRun,
} from '../api/client'
import { fmtDate, fmtDuration, statusColor } from '../lib/utils'
import { useToast } from '../components/ToastProvider'
import { ErrorState, TableSkeleton } from '../components/QueryStates'

/** Maps backend `current_stage` + `status` to the 5-step banner (0..4 = Done). */
function pipelineBannerStageIndex(status: string, currentStage: string | null | undefined): number {
  const st = String(status ?? '').toLowerCase()
  if (st === 'completed' || st === 'cancelled' || st === 'failed') return 4
  const stage = String(currentStage ?? '').toLowerCase()
  if (!stage || stage === 'pending') return 0
  if (stage.includes('screen') || stage === 'screener') return 0
  if (stage.includes('rank') || stage === 'ranker') return 1
  if (stage.includes('stage2') || stage.includes('analysis')) return 2
  if (
    stage.includes('stage3') ||
    stage.includes('decid') ||
    stage.includes('bet') ||
    stage === 'executor'
  ) {
    return 3
  }
  return 0
}

function StatusDot({ status }: { status: string }) {
  if (status === 'running') {
    return <span className="text-yellow">RUNNING</span>
  }
  return <span className={statusColor(status)}>{status?.toUpperCase()}</span>
}

function ActiveBanner({ run, onCancel }: { run: any; onCancel: () => void }) {
  const currentStage = run.current_stage ?? '—'
  const steps = [
    { key: 'screener', label: 'Screener' },
    { key: 'ranker', label: 'Ranker' },
    { key: 'stage2', label: 'Stage 2' },
    { key: 'stage3', label: 'Stage 3' },
    { key: 'done', label: 'Done' },
  ]
  const stageIndex = pipelineBannerStageIndex(run.status, run.current_stage)
  const progress = Math.max(8, Math.min(100, ((stageIndex + 1) / steps.length) * 100))

  return (
    <div className="bg-panel border border-yellow/30 rounded p-4 space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-white">Pipeline running</span>
            <span className="text-xs text-muted truncate">{currentStage}</span>
          </div>
          <div className="mt-2 h-2 w-full rounded bg-card overflow-hidden">
            <div
              className="h-full rounded bg-accent transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
          <div className="mt-2 grid grid-cols-5 gap-2">
            {steps.map((s, i) => (
              <span
                key={s.key}
                className={`text-[10px] ${i <= stageIndex ? 'text-white' : 'text-muted'}`}
              >
                {s.label}
              </span>
            ))}
          </div>
        </div>
        <button
          onClick={onCancel}
          className="text-xs text-red hover:text-red/80 border border-red/30 hover:border-red/60 px-2 py-0.5 rounded transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

export default function Pipeline() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { pushToast } = useToast()
  const [page] = useState(0)
  const [nowTs, setNowTs] = useState(() => Date.now())

  useEffect(() => {
    const t = window.setInterval(() => setNowTs(Date.now()), 1000)
    return () => window.clearInterval(t)
  }, [])

  const { data: activeRun, isLoading: activeLoading, isError: activeError, refetch: refetchActive } = useQuery({
    queryKey: ['active-run'],
    queryFn: fetchActiveRun,
    refetchInterval: 5_000,
  })

  const { data: runs = [], isLoading: runsLoading, isError: runsError, refetch: refetchRuns } = useQuery({
    queryKey: ['runs', page],
    queryFn: () => fetchRuns(),
    refetchInterval: 10_000,
  })

  const { data: scheduler, isLoading: schedulerLoading, isError: schedulerError, refetch: refetchScheduler } = useQuery({
    queryKey: ['scheduler'],
    queryFn: fetchScheduler,
    refetchInterval: 30_000,
  })

  const runMut = useMutation({
    mutationFn: triggerRun,
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['active-run'] })
      qc.invalidateQueries({ queryKey: ['runs'] })
      pushToast('Pipeline run started.', 'success')
      navigate(`/pipeline/${data.run_id}`)
    },
    onError: (err: any) => pushToast(err?.message || 'Failed to start pipeline run.', 'error'),
  })

  const cancelMut = useMutation({
    mutationFn: (id: string) => cancelRun(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['active-run'] })
      qc.invalidateQueries({ queryKey: ['runs'] })
      pushToast('Active run cancelled.', 'info')
    },
    onError: (err: any) => pushToast(err?.message || 'Failed to cancel active run.', 'error'),
  })

  const schedulerEnabled = Boolean(scheduler?.enabled)
  const nextPipelineRunIso = useMemo(() => {
    const jobs = Array.isArray(scheduler?.jobs) ? scheduler.jobs : []
    const job = jobs.find((j: any) => j?.id === 'pipeline_main')
    return job?.next_run ?? null
  }, [scheduler])

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

  const isRunning = activeRun?.status === 'running' || activeRun?.status === 'pending'

  return (
    <div className="space-y-4">
      <div className="sticky top-0 z-20 rounded border border-border bg-base/95 p-3 backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-[180px]">
            <h1 className="text-white font-medium">Pipeline</h1>
            <p className="text-xs text-muted mt-1">
              {isRunning ? 'Active run in progress' : 'No active run'}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {schedulerEnabled ? (
              <div className="bg-panel border border-border rounded px-3 py-2 text-xs">
                <p className="text-muted">Next scheduled run in</p>
                <p className="text-white font-mono mt-0.5">{formatCountdown(nextPipelineRunIso)}</p>
                {nextPipelineRunIso && (
                  <p className="text-muted mt-0.5">at {fmtDate(nextPipelineRunIso)}</p>
                )}
              </div>
            ) : (
              <button
                onClick={() => runMut.mutate(undefined)}
                disabled={runMut.isPending || isRunning}
                className="bg-accent hover:bg-indigo-500 disabled:opacity-50 text-white text-sm px-4 py-1.5 rounded transition-colors"
              >
                {runMut.isPending ? 'Starting...' : 'Run Now'}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Header row */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted">Runs overview</p>
        <p className="text-xs text-muted">Click any row to open details</p>
      </div>

      {(activeError || runsError || schedulerError) && (
        <ErrorState
          message="Failed to load pipeline state."
          onRetry={() => {
            refetchActive()
            refetchRuns()
            refetchScheduler()
          }}
        />
      )}

      {(activeLoading || runsLoading) && <TableSkeleton rows={6} columns={8} />}

      {/* Active run banner */}
      {isRunning && activeRun && (
        <ActiveBanner
          run={activeRun}
          onCancel={() => cancelMut.mutate(activeRun.id)}
        />
      )}

      {/* Runs table */}
      <div className="bg-panel border border-border rounded">
        <div className="px-4 py-3 border-b border-border">
          <p className="text-sm font-medium text-white">Runs</p>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left px-4 py-2 text-xs text-muted font-normal">Started</th>
              <th className="text-left px-4 py-2 text-xs text-muted font-normal">Duration</th>
              <th className="text-left px-4 py-2 text-xs text-muted font-normal">Trigger</th>
              <th className="text-right px-4 py-2 text-xs text-muted font-normal">Screened</th>
              <th className="text-right px-4 py-2 text-xs text-muted font-normal">Ranked</th>
              <th className="text-right px-4 py-2 text-xs text-muted font-normal">Analyzed</th>
              <th className="text-right px-4 py-2 text-xs text-muted font-normal">Bets</th>
              <th className="text-left px-4 py-2 text-xs text-muted font-normal">Status</th>
            </tr>
          </thead>
          <tbody>
            {(runs as any[]).map((r: any) => (
              <tr
                key={r.id}
                onClick={() => navigate(`/pipeline/${r.id}`)}
                className="border-b border-border/50 hover:bg-card/50 transition-colors cursor-pointer"
              >
                <td className="px-4 py-2 text-white font-mono text-xs">{fmtDate(r.started_at)}</td>
                <td className="px-4 py-2 text-muted font-mono text-xs">{fmtDuration(r.started_at, r.finished_at)}</td>
                <td className="px-4 py-2 text-muted text-xs">{r.trigger ?? 'manual'}</td>
                <td className="px-4 py-2 text-right text-muted font-mono text-xs">{r.markets_screened ?? '—'}</td>
                <td className="px-4 py-2 text-right text-muted font-mono text-xs">{r.markets_ranked ?? '—'}</td>
                <td className="px-4 py-2 text-right text-muted font-mono text-xs">{r.markets_analyzed ?? '—'}</td>
                <td className="px-4 py-2 text-right text-muted font-mono text-xs">{r.bets_placed ?? '—'}</td>
                <td className="px-4 py-2 text-xs">
                  <StatusDot status={r.status} />
                </td>
              </tr>
            ))}
            {(runs as any[]).length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-6 text-center text-muted text-sm">No runs yet</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
