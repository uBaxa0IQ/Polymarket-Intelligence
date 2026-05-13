import { useState, useEffect, createContext, useContext } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchSettings, updateSetting, clearToken } from '../api/client'
import { useToast } from './ToastProvider'

// ── Execution context (safety toggle) ─────────────────────────────────────────

interface ExecCtx {
  executionEnabled: boolean
  toggle: () => void
}
const ExecContext = createContext<ExecCtx>({ executionEnabled: false, toggle: () => {} })
export const useExecution = () => useContext(ExecContext)

// ── Nav items ─────────────────────────────────────────────────────────────────

const NAV = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/pipeline', label: 'Pipeline', end: false },
  { to: '/bets', label: 'Bets', end: false },
  { to: '/copy-trading', label: 'Copy Trading', end: false },
  { to: '/settings', label: 'Settings', end: false },
]

// ── Layout ────────────────────────────────────────────────────────────────────

export default function Layout({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const { pushToast } = useToast()
  const [executionEnabled, setExecutionEnabled] = useState(false)

  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: fetchSettings,
    refetchInterval: 20_000,
  })

  useEffect(() => {
    const bets = (settings as any)?.betting
    if (Array.isArray(bets)) {
      const row = bets.find((r: any) => r.key === 'execution_enabled')
      if (row != null) setExecutionEnabled(Boolean(row.value))
    }
  }, [settings])

  const toggleMut = useMutation({
    mutationFn: () => updateSetting('betting', 'execution_enabled', !executionEnabled),
    onSuccess: () => {
      setExecutionEnabled(v => !v)
      qc.invalidateQueries({ queryKey: ['settings'] })
      pushToast(`Execution ${executionEnabled ? 'disabled' : 'enabled'}.`, executionEnabled ? 'info' : 'success')
    },
    onError: (err: any) => pushToast(err?.message || 'Failed to update execution mode.', 'error'),
  })

  function handleLogout() {
    clearToken()
    navigate('/login')
  }

  return (
    <ExecContext.Provider value={{ executionEnabled, toggle: () => toggleMut.mutate() }}>
      <div className="flex h-screen overflow-hidden">
        {/* Sidebar */}
        <aside className="flex flex-col w-52 bg-panel border-r border-border shrink-0">
          {/* Logo */}
          <div className="px-4 py-4 border-b border-border">
            <span className="text-white font-semibold text-sm tracking-wide">PM Intel</span>
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-2 py-3 space-y-0.5">
            {NAV.map(({ to, label, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  `flex items-center px-3 py-2 rounded text-sm transition-colors ${
                    isActive
                      ? 'bg-card text-white'
                      : 'text-muted hover:text-white hover:bg-card/60'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>

          {/* Bottom controls */}
          <div className="px-2 py-3 border-t border-border space-y-1">
            {/* Safety toggle */}
            <button
              onClick={() => toggleMut.mutate()}
              disabled={toggleMut.isPending}
              className={`w-full flex items-center justify-between px-3 py-2 rounded text-xs font-mono font-medium transition-colors ${
                executionEnabled
                  ? 'bg-accent/20 border border-accent/40 text-indigo-200 hover:bg-accent/30'
                  : 'bg-card border border-border text-muted hover:text-white hover:border-muted'
              }`}
            >
              <span>MODE</span>
              <span>{executionEnabled ? 'LIVE' : 'DRY'}</span>
            </button>

            <button
              onClick={handleLogout}
              className="w-full flex items-center px-3 py-2 rounded text-sm text-muted hover:text-white hover:bg-card/60 transition-colors"
            >
              Sign out
            </button>
          </div>
        </aside>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto bg-base">
          <div className="p-6">{children}</div>
        </main>
      </div>
    </ExecContext.Provider>
  )
}
