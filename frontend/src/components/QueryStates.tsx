export function LoadingState({ label = 'Loading...' }: { label?: string }) {
  return (
    <div className="rounded border border-border bg-panel px-4 py-6 text-center text-sm text-muted">
      {label}
    </div>
  )
}

export function TableSkeleton({
  rows = 6,
  columns = 6,
}: {
  rows?: number
  columns?: number
}) {
  return (
    <div className="rounded border border-border bg-panel p-4">
      <div className="space-y-2 animate-pulse">
        {Array.from({ length: rows }).map((_, rIdx) => (
          <div key={rIdx} className="grid gap-2" style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}>
            {Array.from({ length: columns }).map((__, cIdx) => (
              <div key={cIdx} className="h-4 rounded bg-card" />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

export function ErrorState({
  message = 'Failed to load data.',
  onRetry,
}: {
  message?: string
  onRetry?: () => void
}) {
  return (
    <div className="rounded border border-red/40 bg-panel px-4 py-6 text-center">
      <p className="text-sm text-red">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded border border-red/40 px-3 py-1 text-xs text-red hover:bg-red/10"
        >
          Retry
        </button>
      )}
    </div>
  )
}

export function EmptyState({ label }: { label: string }) {
  return (
    <div className="rounded border border-border bg-panel px-4 py-6 text-center text-sm text-muted">
      {label}
    </div>
  )
}
