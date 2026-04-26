export function fmt(n: number | null | undefined, decimals = 2): string {
  if (n == null) return '—'
  return n.toFixed(decimals)
}

export function fmtUsd(n: number | null | undefined): string {
  if (n == null) return '—'
  const abs = Math.abs(n)
  const formatted = abs >= 1000 ? `$${(abs / 1000).toFixed(1)}k` : `$${abs.toFixed(2)}`
  return n < 0 ? `-${formatted}` : formatted
}

export function fmtPct(n: number | null | undefined): string {
  if (n == null) return '—'
  return `${(n * 100).toFixed(1)}%`
}

/** Alias for fmtPct — used in tables (probability as %). */
export const pct = fmtPct

export function gapColor(gap: number | null | undefined): string {
  if (gap == null || Number.isNaN(gap)) return 'text-muted'
  if (gap > 0.005) return 'text-green'
  if (gap < -0.005) return 'text-red'
  return 'text-muted'
}

export function actionBadge(action: string | null | undefined): string {
  if (action === 'bet_yes') return 'bg-green/20 text-green text-xs px-2 py-0.5 rounded-full font-medium'
  if (action === 'bet_no') return 'bg-red/20 text-red text-xs px-2 py-0.5 rounded-full font-medium'
  if (action === 'skip') return 'bg-border text-muted text-xs px-2 py-0.5 rounded-full font-medium'
  return 'bg-card text-muted text-xs px-2 py-0.5 rounded-full font-medium'
}

export function fmtTokens(n: number | null | undefined): string {
  if (n == null) return '—'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return '—'
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60_000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  })
}

function parseByDate(question: string | null | undefined): Date | null {
  if (!question) return null
  const m = question.match(/\bby\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})\b/i)
  if (!m) return null
  const d = new Date(`${m[1]} 00:00:00`)
  return Number.isNaN(d.getTime()) ? null : d
}

/**
 * Polymarket "by <date>" questions often resolve at the end of that date.
 * UI heuristic: if end_date falls on the same calendar day very early (e.g. 03:00),
 * show next day to match user expectation of "by end of day".
 */
export function fmtMarketEndDate(
  iso: string | null | undefined,
  question: string | null | undefined,
): string {
  if (!iso) return '—'
  const end = new Date(iso)
  if (Number.isNaN(end.getTime())) return '—'
  const byDate = parseByDate(question)
  if (!byDate) {
    // Fallback for rows where question text is unavailable (only market_id in payload):
    // Polymarket date-only markets often appear as early-hour timestamps (e.g. 03:00).
    // Display +1 day to reflect "by end of day" semantics in the UI.
    if (end.getHours() <= 6 && end.getMinutes() === 0) {
      const shifted = new Date(end)
      shifted.setDate(shifted.getDate() + 1)
      return shifted.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      })
    }
    return fmtDate(iso)
  }

  const sameDay =
    end.getFullYear() === byDate.getFullYear() &&
    end.getMonth() === byDate.getMonth() &&
    end.getDate() === byDate.getDate()

  if (sameDay && end.getHours() <= 6) {
    const shifted = new Date(end)
    shifted.setDate(shifted.getDate() + 1)
    return shifted.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
  }

  return fmtDate(iso)
}

export function fmtDuration(started: string | null, finished: string | null): string {
  if (!started) return '—'
  const end = finished ? new Date(finished) : new Date()
  const sec = Math.floor((end.getTime() - new Date(started).getTime()) / 1000)
  if (sec < 60) return `${sec}s`
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${m}m ${s}s`
}

export function statusColor(status: string): string {
  switch (status) {
    case 'completed': return 'text-green'
    case 'failed':    return 'text-red'
    case 'running':   return 'text-yellow'
    case 'cancelled': return 'text-muted'
    default:          return 'text-muted'
  }
}

export function betStatusColor(status: string): string {
  switch (status) {
    case 'filled':  return 'text-green'
    case 'pending': return 'text-yellow'
    case 'dry_run': return 'text-muted'
    case 'failed':  return 'text-red'
    default:        return 'text-muted'
  }
}

export function actionColor(action: string | null): string {
  if (action === 'bet_yes') return 'text-green'
  if (action === 'bet_no')  return 'text-red'
  return 'text-muted'
}

export function priorityColor(p: string | null): string {
  if (p === 'high')   return 'text-green'
  if (p === 'medium') return 'text-yellow'
  return 'text-muted'
}

export function pnlColor(pnl: number | null | undefined): string {
  if (pnl == null) return 'text-muted'
  return pnl >= 0 ? 'text-green' : 'text-red'
}
