import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  fetchSettings,
  updateSetting,
  resetSettingsDefaults,
  fetchPrompts,
  updatePrompt,
  resetPromptsDefaults,
  fetchTokenStats,
  resetRuntimeData,
  syncBetSettlements,
  fetchPolymarketServerGeoblock,
  fetchPolymarketClobHealth,
} from '../api/client'
import { useEffect, useMemo, useState } from 'react'
import { fmtDate, fmtTokens, fmtUsd } from '../lib/utils'
import { useToast } from '../components/ToastProvider'
import { ErrorState, LoadingState, TableSkeleton } from '../components/QueryStates'
import { SettingHelpDrawer, SettingHelpTrigger } from '../components/SettingHelpDrawer'

const CATEGORIES = ['screener', 'ranker', 'stage2', 'stage3', 'scheduler', 'betting', 'risk', 'copytrading', 'llm'] as const
type Cat = (typeof CATEGORIES)[number]
type SettingsSection = 'settings' | 'prompts' | 'token_usage' | 'maintenance'

function SettingField({
  cat,
  setting,
  onSave,
  onNotify,
  onStatusChange,
}: {
  cat: string
  setting: any
  onSave: () => void
  onNotify: (message: string, tone?: 'success' | 'error' | 'info') => void
  onStatusChange: (fieldId: string, status: 'idle' | 'unsaved' | 'saving' | 'error') => void
}) {
  const isValidEthWallet = (v: string) => /^0x[a-fA-F0-9]{40}$/.test(v)
  const parseTargetWalletsValue = (raw: string): string[] => {
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed)) return []
      const out: string[] = []
      for (const row of parsed) {
        const w = String(row ?? '').trim().toLowerCase()
        if (isValidEthWallet(w) && !out.includes(w)) out.push(w)
      }
      return out
    } catch {
      return []
    }
  }
  const initialValue =
    typeof setting.value === 'object' ? JSON.stringify(setting.value, null, 2) : String(setting.value ?? '')
  const [value, setValue] = useState(initialValue)
  const [walletDraft, setWalletDraft] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSave = async (nextValue?: string) => {
    const toSave = nextValue ?? value
    if (toSave === initialValue) return
    setSaving(true)
    setError(null)
    try {
      if (isCopyTradingTargetWallets) {
        let parsedWallets: unknown
        try {
          parsedWallets = JSON.parse(toSave)
        } catch {
          throw new Error('target_wallets must be valid JSON array, e.g. ["0x...","0x..."]')
        }
        if (!Array.isArray(parsedWallets)) {
          throw new Error('target_wallets must be a JSON array')
        }
        const bad = parsedWallets.find((row: unknown) => !isValidEthWallet(String(row ?? '').trim()))
        if (bad !== undefined) {
          throw new Error(`Invalid wallet in target_wallets: ${String(bad)}`)
        }
      }
      let parsed: any = toSave
      try {
        parsed = JSON.parse(toSave)
      } catch {
        /* keep string */
      }
      await updateSetting(cat, setting.key, parsed)
      onSave()
      setValue(toSave)
      onNotify(`Saved: ${cat}.${setting.key}`, 'success')
    } catch (e: any) {
      setError(e?.message || 'Failed to save')
      onNotify(e?.message || `Failed to save ${cat}.${setting.key}`, 'error')
    } finally {
      setSaving(false)
    }
  }

  const isSecret =
    setting.key.includes('key') ||
    setting.key.includes('secret') ||
    setting.key.includes('password') ||
    setting.key.includes('passphrase') ||
    setting.key.includes('private')
  const isRankerSelectionPolicy = cat === 'ranker' && setting.key === 'selection_policy'
  const isProviderSetting = (cat === 'ranker' || cat === 'stage2') && setting.key === 'provider'
  const isOrderTimeInForceSetting = cat === 'betting' && setting.key === 'order_time_in_force'
  const isDryRunBankrollSource = cat === 'betting' && setting.key === 'dry_run_bankroll_source'
  const isStage2AnalysisMode = cat === 'stage2' && setting.key === 'mode'
  const isCopyTradingStakeMode = cat === 'copytrading' && setting.key === 'stake_mode'
  const isCopyTradingTargetWallets = cat === 'copytrading' && setting.key === 'target_wallets'
  const isComplexValue = setting.value !== null && typeof setting.value === 'object'
  const dirty = value !== initialValue
  const fieldId = `${cat}:${setting.key}`
  const [showJsonEditor, setShowJsonEditor] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)

  useEffect(() => {
    setValue(initialValue)
  }, [cat, setting.key, initialValue])

  const wallets = isCopyTradingTargetWallets ? parseTargetWalletsValue(value) : []

  useEffect(() => {
    const status: 'idle' | 'unsaved' | 'saving' | 'error' =
      saving ? 'saving' : error ? 'error' : dirty ? 'unsaved' : 'idle'
    onStatusChange(fieldId, status)
    return () => onStatusChange(fieldId, 'idle')
  }, [saving, error, dirty, fieldId, onStatusChange])

  return (
    <div className="bg-gray-900/50 border border-gray-800 rounded-lg px-3 py-2">
      <div className={`flex gap-3 ${isCopyTradingTargetWallets ? 'flex-col' : 'items-center justify-between'}`}>
        <div className="min-w-0">
          <div className="flex items-center gap-2 min-w-0">
            <p className="text-xs font-mono text-gray-200 truncate">{setting.key}</p>
            <SettingHelpTrigger
              category={cat}
              settingKey={setting.key}
              serverDescription={setting.description}
              onOpen={() => setHelpOpen(true)}
            />
            <span
              className={`text-[10px] uppercase tracking-wide ${
                saving ? 'text-yellow-400' : error ? 'text-red-400' : 'text-orange-400'
              }`}
            >
              {saving ? 'saving' : error ? 'error' : dirty ? 'unsaved' : ''}
            </span>
          </div>
          {setting.description && <p className="text-[11px] text-gray-500 truncate">{setting.description}</p>}
        </div>
        <div className={isCopyTradingTargetWallets ? 'w-full' : 'w-72 max-w-[45%]'}>
          {typeof setting.value === 'boolean' ? (
            <button
              type="button"
              onClick={() => {
                const next = String(value !== 'true')
                setValue(next)
                void handleSave(next)
              }}
              className={`w-full flex items-center justify-between rounded px-2 py-1.5 border text-xs ${
                value === 'true'
                  ? 'bg-indigo-600/20 border-indigo-500/40 text-indigo-200'
                  : 'bg-gray-900 border-gray-700 text-gray-300'
              }`}
            >
              <span>{value === 'true' ? 'Enabled' : 'Disabled'}</span>
              <span
                className={`relative inline-flex h-4 w-7 items-center rounded-full transition-colors ${
                  value === 'true' ? 'bg-accent' : 'bg-border'
                }`}
              >
                <span
                  className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${
                    value === 'true' ? 'translate-x-3.5' : 'translate-x-0.5'
                  }`}
                />
              </span>
            </button>
          ) : isRankerSelectionPolicy ? (
            <select
              value={value || 'top_n'}
              onChange={e => {
                const next = e.target.value
                setValue(next)
                void handleSave(next)
              }}
              className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 font-mono focus:border-indigo-500 outline-none"
            >
              <option value="top_n">top_n</option>
              <option value="high_only">high_only</option>
              <option value="high_medium">high_medium</option>
            </select>
          ) : isProviderSetting ? (
            <select
              value={value || 'yandex'}
              onChange={e => {
                const next = e.target.value
                setValue(next)
                void handleSave(next)
              }}
              className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 font-mono focus:border-indigo-500 outline-none"
            >
              <option value="yandex">yandex</option>
              <option value="anthropic">anthropic</option>
            </select>
          ) : isOrderTimeInForceSetting ? (
            <select
              value={value || 'IOC'}
              onChange={e => {
                const next = e.target.value
                setValue(next)
                void handleSave(next)
              }}
              className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 font-mono focus:border-indigo-500 outline-none"
            >
              <option value="IOC">IOC (→ FAK in CLOB client)</option>
              <option value="FAK">FAK (fill and kill)</option>
              <option value="FOK">FOK (fill or kill all)</option>
              <option value="GTC">GTC (resting until cancel)</option>
              <option value="GTD">GTD (good-til-date; needs expiration in order — advanced)</option>
            </select>
          ) : isDryRunBankrollSource ? (
            <select
              value={value || 'clob'}
              onChange={e => {
                const next = e.target.value
                setValue(next)
                void handleSave(next)
              }}
              className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 font-mono focus:border-indigo-500 outline-none"
            >
              <option value="clob">clob — CLOB account balance</option>
              <option value="settings">settings — stage3.bankroll_usd (paper)</option>
            </select>
          ) : isStage2AnalysisMode ? (
            <button
              type="button"
              onClick={() => {
                const current = value === 'simple' ? 'simple' : 'full'
                const next = current === 'full' ? 'simple' : 'full'
                setValue(next)
                void handleSave(next)
              }}
              className={`w-full flex items-center justify-between rounded px-2 py-1.5 border text-xs gap-2 ${
                value !== 'simple'
                  ? 'bg-indigo-600/20 border-indigo-500/40 text-indigo-200'
                  : 'bg-gray-900 border-gray-700 text-gray-300'
              }`}
            >
              <span className="text-left min-w-0 leading-tight">
                <span className="block font-medium">
                  {value === 'simple' ? 'Simple' : 'Full'}
                </span>
                <span className="block text-[10px] text-gray-500 font-normal">
                  {value === 'simple' ? 'Single agent + web search' : 'News + debate + judge'}
                </span>
              </span>
              <span
                className={`relative inline-flex h-4 w-7 shrink-0 items-center rounded-full transition-colors ${
                  value !== 'simple' ? 'bg-accent' : 'bg-border'
                }`}
                aria-hidden
              >
                <span
                  className={`inline-block h-3 w-3 transform rounded-full bg-white transition-transform ${
                    value !== 'simple' ? 'translate-x-3.5' : 'translate-x-0.5'
                  }`}
                />
              </span>
            </button>
          ) : isCopyTradingStakeMode ? (
            <select
              value={value || 'fixed'}
              onChange={e => {
                const next = e.target.value
                setValue(next)
                void handleSave(next)
              }}
              className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 font-mono focus:border-indigo-500 outline-none"
            >
              <option value="fixed">fixed</option>
              <option value="balance_pct">balance_pct</option>
              <option value="follow_trader_size">follow_trader_size</option>
              <option value="follow_trader_bank_pct">follow_trader_bank_pct</option>
            </select>
          ) : isCopyTradingTargetWallets ? (
            <div className="space-y-2">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={walletDraft}
                  onChange={e => setWalletDraft(e.target.value)}
                  placeholder="0x..."
                  className="flex-1 bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 font-mono focus:border-indigo-500 outline-none"
                />
                <button
                  type="button"
                  onClick={() => {
                    const nextWallet = walletDraft.trim().toLowerCase()
                    if (!isValidEthWallet(nextWallet)) {
                      setError('Wallet must be 0x + 40 hex chars')
                      return
                    }
                    if (wallets.includes(nextWallet)) {
                      setError('Wallet already exists in target_wallets')
                      return
                    }
                    const next = JSON.stringify([...wallets, nextWallet], null, 2)
                    setError(null)
                    setWalletDraft('')
                    setValue(next)
                    void handleSave(next)
                  }}
                  className="text-xs bg-indigo-700 hover:bg-indigo-600 text-white px-3 py-1.5 rounded"
                >
                  Add
                </button>
              </div>
              <div className="space-y-1">
                {wallets.map(w => (
                  <div key={w} className="flex items-center justify-between gap-2 bg-gray-900 border border-gray-800 rounded px-2 py-1.5">
                    <span className="text-xs text-gray-200 font-mono truncate">{w}</span>
                    <button
                      type="button"
                      onClick={() => {
                        const next = JSON.stringify(wallets.filter(x => x !== w), null, 2)
                        setError(null)
                        setValue(next)
                        void handleSave(next)
                      }}
                      className="text-[11px] text-red-300 hover:text-red-200"
                    >
                      Remove
                    </button>
                  </div>
                ))}
                {wallets.length === 0 ? <p className="text-[11px] text-gray-500">No wallets added yet.</p> : null}
              </div>
            </div>
          ) : isComplexValue ? (
            <div className="flex items-center justify-end gap-2">
              <p className="text-[11px] text-gray-400 truncate max-w-[220px] text-right">
                {value.replace(/\s+/g, ' ').slice(0, 80)}
              </p>
              <button
                type="button"
                onClick={() => setShowJsonEditor(true)}
                className="text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 px-2.5 py-1 rounded"
              >
                Edit
              </button>
            </div>
          ) : (
            <input
              type={isSecret ? 'password' : 'text'}
              value={value}
              onChange={e => setValue(e.target.value)}
              onBlur={() => {
                if (isCopyTradingTargetWallets) {
                  try {
                    const parsed = JSON.parse(value)
                    if (!Array.isArray(parsed)) {
                      setError('target_wallets must be a JSON array')
                      return
                    }
                    const bad = parsed.find((row: unknown) => !isValidEthWallet(String(row ?? '').trim()))
                    if (bad !== undefined) {
                      setError(`Invalid wallet in target_wallets: ${String(bad)}`)
                      return
                    }
                  } catch {
                    setError('target_wallets must be valid JSON array, e.g. ["0x...","0x..."]')
                    return
                  }
                }
                void handleSave()
              }}
              className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-xs text-gray-200 font-mono focus:border-indigo-500 outline-none"
            />
          )}
        </div>
      </div>
      {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
      <SettingHelpDrawer
        open={helpOpen}
        onClose={() => setHelpOpen(false)}
        category={cat}
        settingKey={setting.key}
        serverDescription={setting.description}
      />
      {showJsonEditor && (
        <div
          className="fixed inset-0 z-50 bg-black/70 p-4 flex items-center justify-center"
          onClick={() => setShowJsonEditor(false)}
        >
          <div
            className="w-full max-w-4xl max-h-[90vh] overflow-hidden bg-panel border border-border rounded-xl"
            onClick={e => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <p className="text-sm font-mono text-indigo-300">{cat}.{setting.key}</p>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowJsonEditor(false)}
                  className="text-xs text-muted hover:text-white px-2 py-1"
                >
                  Close
                </button>
                <button
                  type="button"
                  onClick={() => void handleSave()}
                  disabled={!dirty || saving}
                  className="text-xs bg-accent hover:bg-indigo-500 disabled:opacity-60 text-white px-3 py-1.5 rounded"
                >
                  {saving ? 'Saving...' : 'Save'}
                </button>
              </div>
            </div>
            <div className="p-4 space-y-2">
              <textarea
                value={value}
                onChange={e => setValue(e.target.value)}
                rows={20}
                autoComplete="off"
                autoCorrect="off"
                spellCheck={false}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-xs text-gray-200 font-mono focus:border-indigo-500 outline-none resize-y min-h-[420px]"
              />
              {error && <p className="text-xs text-red-400">{error}</p>}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function PromptEditorModal({
  row,
  onClose,
  onSaved,
  onNotify,
}: {
  row: any
  onClose: () => void
  onSaved: () => void
  onNotify: (message: string, tone?: 'success' | 'error' | 'info') => void
}) {
  const initialTemplate = row?.template ?? ''
  const [template, setTemplate] = useState(initialTemplate)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const dirty = template !== initialTemplate

  const handleSave = async () => {
    if (!dirty) return
    setSaving(true)
    setError(null)
    try {
      await updatePrompt(row.name, template)
      onSaved()
      onNotify(`Saved prompt: ${row.name}`, 'success')
      onClose()
    } catch (e: any) {
      setError(e?.message || 'Failed to save')
      onNotify(e?.message || `Failed to save prompt ${row.name}`, 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/70 p-4 flex items-center justify-center" onClick={onClose}>
      <div className="w-full max-w-6xl max-h-[95vh] overflow-hidden bg-panel border border-border rounded-xl" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <p className="text-sm font-mono text-indigo-300">{row.name}</p>
          <div className="flex items-center gap-2">
            <button type="button" onClick={onClose} className="text-xs text-muted hover:text-white px-2 py-1">
              Close
            </button>
            <button
              type="button"
              onClick={() => void handleSave()}
              disabled={!dirty || saving}
              className="text-xs bg-accent hover:bg-indigo-500 disabled:opacity-60 text-white px-3 py-1.5 rounded"
            >
              {saving ? 'Saving...' : 'Save'}
            </button>
          </div>
        </div>
        <div className="p-4 space-y-2">
          <textarea
            value={template}
            onChange={e => setTemplate(e.target.value)}
            rows={30}
            autoComplete="off"
            autoCorrect="off"
            spellCheck={false}
            className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-xs text-gray-200 font-mono focus:border-indigo-500 outline-none resize-y min-h-[600px]"
          />
          {error && <p className="text-xs text-red-400">{error}</p>}
        </div>
      </div>
    </div>
  )
}

export default function Settings() {
  const qc = useQueryClient()
  const { pushToast } = useToast()
  const [section, setSection] = useState<SettingsSection>('settings')
  const [cat, setCat] = useState<Cat>('screener')
  const [settingsMode, setSettingsMode] = useState<'basic' | 'advanced'>('basic')
  const [settingsSearch, setSettingsSearch] = useState('')
  const [promptSearch, setPromptSearch] = useState('')
  const [activePrompt, setActivePrompt] = useState<any | null>(null)
  const [fieldStatuses, setFieldStatuses] = useState<Record<string, 'idle' | 'unsaved' | 'saving' | 'error'>>({})
  const { data: settings, isLoading, isError: settingsError, refetch: refetchSettings } = useQuery({ queryKey: ['settings'], queryFn: fetchSettings })
  const { data: prompts = [], isLoading: promptsLoading, isError: promptsError, refetch: refetchPrompts } = useQuery({
    queryKey: ['prompts'],
    queryFn: fetchPrompts,
    enabled: section === 'prompts',
  })
  const [resetting, setResetting] = useState(false)
  const [resettingPrompts, setResettingPrompts] = useState(false)
  const [tokenPeriod, setTokenPeriod] = useState<'today' | '7d' | '30d' | 'all'>('today')
  const { data: tokenStats, isLoading: tokensLoading, isError: tokensError, refetch: refetchTokenStats } = useQuery({
    queryKey: ['token-stats', tokenPeriod],
    queryFn: () => fetchTokenStats(tokenPeriod),
    enabled: section === 'token_usage',
  })
  const [runtimeResetting, setRuntimeResetting] = useState(false)
  const [syncingSettlements, setSyncingSettlements] = useState(false)
  const [geoblockLoading, setGeoblockLoading] = useState(false)
  const [geoblockError, setGeoblockError] = useState<string | null>(null)
  const [geoblockResult, setGeoblockResult] = useState<{
    blocked: boolean
    ip?: string
    country?: string
    region?: string
  } | null>(null)
  const [clobHealthLoading, setClobHealthLoading] = useState(false)
  const [clobHealthError, setClobHealthError] = useState<string | null>(null)
  const [clobHealthResult, setClobHealthResult] = useState<{
    ok: boolean
    latency_ms: number
    wallet_address?: string | null
    has_balance_payload: boolean
  } | null>(null)

  const handleReset = async () => {
    if (!confirm('Reset all settings to defaults?')) return
    setResetting(true)
    try {
      await resetSettingsDefaults()
      qc.invalidateQueries({ queryKey: ['settings'] })
      await qc.invalidateQueries({ queryKey: ['prompts'] })
      await qc.invalidateQueries({ queryKey: ['scheduler'] })
      pushToast('Settings reset to defaults.', 'success')
    } catch (e: any) {
      pushToast(e?.message || 'Failed to reset settings.', 'error')
    } finally {
      setResetting(false)
    }
  }

  const handleResetPrompts = async () => {
    if (!confirm('Reset all prompts to defaults?')) return
    setResettingPrompts(true)
    try {
      await resetPromptsDefaults()
      qc.invalidateQueries({ queryKey: ['prompts'] })
      pushToast('Prompts reset to defaults.', 'success')
    } catch (e: any) {
      pushToast(e?.message || 'Failed to reset prompts.', 'error')
    } finally {
      setResettingPrompts(false)
    }
  }

  const catSettings = (settings?.[cat] ?? []) as any[]
  const allSettings = settings ?? {}
  const timingRows = Object.entries(allSettings)
    .flatMap(([categoryName, rows]) =>
      (rows as any[])
        .filter(row => /(interval|timeout|retry|backoff|delay|cooldown|poll)/i.test(String(row?.key ?? '')))
        .map(row => ({
          category: categoryName,
          key: row.key,
          value: row.value,
          description: row.description,
        })),
    )

  const basicSettingKeys = useMemo(
    () =>
      new Set([
        'enabled',
        'run_immediately_on_enable',
        'interval_hours',
        'selection_policy',
        'top_n',
        'provider',
        'order_time_in_force',
        'gap_threshold',
        'max_bet_fraction',
        'mode',
        'target_wallet',
        'target_wallets',
        'stake_mode',
        'min_bet_usd',
        'poll_seconds',
        'live',
        'binary_only',
      ]),
    [],
  )

  const basicRowsByCategory = useMemo(() => {
    const order: Cat[] = ['scheduler', 'ranker', 'stage2', 'stage3', 'copytrading']
    return order
      .map(category => {
        const rows = ((allSettings[category] ?? []) as any[]).filter((s: any) =>
          basicSettingKeys.has(String(s.key)),
        )
        return { category, rows }
      })
      .filter(group => group.rows.length > 0)
  }, [allSettings, basicSettingKeys])

  const settingsGlobalStatus = useMemo(() => {
    const values = Object.values(fieldStatuses)
    if (values.some(v => v === 'error')) return { label: 'Some fields failed', tone: 'text-red-400' }
    if (values.some(v => v === 'saving')) return { label: 'Saving...', tone: 'text-yellow-400' }
    if (values.some(v => v === 'unsaved')) return { label: 'Unsaved changes', tone: 'text-orange-400' }
    return { label: 'All changes saved', tone: 'text-emerald-400' }
  }, [fieldStatuses])

  const handleStatusChange = (fieldId: string, status: 'idle' | 'unsaved' | 'saving' | 'error') => {
    setFieldStatuses(prev => ({ ...prev, [fieldId]: status }))
  }

  const visibleSettings = useMemo(() => {
    const query = settingsSearch.trim().toLowerCase()
    return catSettings.filter((s: any) => {
      if (!query) return true
      const haystack = `${s.key} ${s.description || ''}`.toLowerCase()
      return haystack.includes(query)
    })
  }, [catSettings, settingsSearch])

  const invalidateRuntimeQueries = async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ['bets'] }),
      qc.invalidateQueries({ queryKey: ['decisions'] }),
      qc.invalidateQueries({ queryKey: ['summary'] }),
      qc.invalidateQueries({ queryKey: ['pnl-chart'] }),
      qc.invalidateQueries({ queryKey: ['activity'] }),
      qc.invalidateQueries({ queryKey: ['runs'] }),
      qc.invalidateQueries({ queryKey: ['active-run'] }),
      qc.invalidateQueries({ queryKey: ['run'] }),
      qc.invalidateQueries({ queryKey: ['run-screener'] }),
      qc.invalidateQueries({ queryKey: ['run-ranker'] }),
      qc.invalidateQueries({ queryKey: ['run-analyses'] }),
      qc.invalidateQueries({ queryKey: ['run-llm'] }),
      qc.invalidateQueries({ queryKey: ['token-stats'] }),
      qc.invalidateQueries({ queryKey: ['wallet-summary'] }),
      qc.invalidateQueries({ queryKey: ['market'] }),
      qc.invalidateQueries({ queryKey: ['markets'] }),
    ])
  }

  const handleRuntimeReset = async () => {
    if (!confirm('This will delete all runtime data (history, pipeline runs, analyses, stats). Continue?')) return
    const guard = prompt('Type DELETE to confirm full runtime reset')
    if (guard !== 'DELETE') {
      alert('Runtime reset cancelled. Confirmation phrase did not match.')
      return
    }
    setRuntimeResetting(true)
    try {
      await resetRuntimeData()
      await invalidateRuntimeQueries()
      pushToast('Runtime data was reset. Settings and prompts were preserved.', 'success')
    } catch (e: any) {
      pushToast(e?.message || String(e), 'error')
    } finally {
      setRuntimeResetting(false)
    }
  }

  const handlePolymarketGeoblockCheck = async () => {
    setGeoblockLoading(true)
    setGeoblockError(null)
    try {
      const r = await fetchPolymarketServerGeoblock()
      setGeoblockResult(r)
      pushToast(
        r.blocked
          ? 'Polymarket reports this server IP as geoblocked for trading.'
          : 'Polymarket reports this server IP as allowed (not geoblocked).',
        r.blocked ? 'error' : 'success',
      )
    } catch (e: any) {
      const msg = e?.message || String(e)
      setGeoblockError(msg)
      setGeoblockResult(null)
      pushToast(msg, 'error')
    } finally {
      setGeoblockLoading(false)
    }
  }

  const handleManualSettlementSync = async () => {
    setSyncingSettlements(true)
    try {
      const r = await syncBetSettlements()
      pushToast(
        `Settlements sync complete: settled ${r.settled}, skipped ${r.skipped}, errors ${r.errors}.`,
        'success',
      )
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['bets'] }),
        qc.invalidateQueries({ queryKey: ['summary'] }),
        qc.invalidateQueries({ queryKey: ['pnl-chart'] }),
      ])
    } catch (e: any) {
      pushToast(e?.message || String(e), 'error')
    } finally {
      setSyncingSettlements(false)
    }
  }

  const handlePolymarketClobHealthCheck = async () => {
    setClobHealthLoading(true)
    setClobHealthError(null)
    try {
      const r = await fetchPolymarketClobHealth()
      setClobHealthResult(r)
      pushToast(
        r.ok
          ? `CLOB health OK (${r.latency_ms} ms).`
          : `CLOB health check returned degraded status (${r.latency_ms} ms).`,
        r.ok ? 'success' : 'error',
      )
    } catch (e: any) {
      const msg = e?.message || String(e)
      setClobHealthError(msg)
      setClobHealthResult(null)
      pushToast(msg, 'error')
    } finally {
      setClobHealthLoading(false)
    }
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <h2 className="text-xl font-bold">Settings</h2>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void handleReset()}
            disabled={resetting}
            className="bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm px-3 py-2 rounded-lg border border-gray-700"
          >
            {resetting ? 'Resetting…' : 'Reset Defaults'}
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 border-b border-gray-800 pb-3">
        <button
          type="button"
          onClick={() => setSection('settings')}
          className={`text-sm px-4 py-2 rounded-lg transition-colors ${
            section === 'settings' ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'
          }`}
        >
          Parameters
        </button>
        <button
          type="button"
          onClick={() => setSection('prompts')}
          className={`text-sm px-4 py-2 rounded-lg transition-colors ${
            section === 'prompts' ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'
          }`}
        >
          Prompts
        </button>
        <button
          type="button"
          onClick={() => setSection('token_usage')}
          className={`text-sm px-4 py-2 rounded-lg transition-colors ${
            section === 'token_usage' ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'
          }`}
        >
          Token Usage
        </button>
        <button
          type="button"
          onClick={() => setSection('maintenance')}
          className={`text-sm px-4 py-2 rounded-lg transition-colors ${
            section === 'maintenance' ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'
          }`}
        >
          Maintenance
        </button>
      </div>

      {section === 'prompts' && (
        <div className="space-y-4">
          <div className="flex justify-between gap-3 flex-wrap">
            <input
              type="text"
              placeholder="Search prompt..."
              value={promptSearch}
              onChange={e => setPromptSearch(e.target.value)}
              autoComplete="off"
              autoCorrect="off"
              spellCheck={false}
              name="prompts-search"
              className="bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 outline-none focus:border-indigo-500 w-72 max-w-full"
            />
            <button
              type="button"
              onClick={() => void handleResetPrompts()}
              disabled={resettingPrompts}
              className="text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 px-3 py-2 rounded-lg"
            >
              {resettingPrompts ? '...' : 'Reset prompts to defaults'}
            </button>
          </div>
          {promptsLoading ? (
            <LoadingState label="Loading prompts..." />
          ) : promptsError ? (
            <ErrorState message="Failed to load prompts." onRetry={() => refetchPrompts()} />
          ) : (
            <div className="space-y-2">
              {prompts
                .filter((p: any) => String(p.name || '').toLowerCase().includes(promptSearch.trim().toLowerCase()))
                .map((p: any) => (
                  <div key={p.name} className="bg-gray-900/50 border border-gray-800 rounded-lg px-3 py-2">
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-xs font-mono text-indigo-300 truncate">{p.name}</p>
                        <p className="text-[11px] text-gray-500 truncate">{String(p.template || '').slice(0, 120) || 'Empty prompt'}</p>
                      </div>
                      <button
                        type="button"
                        onClick={() => setActivePrompt(p)}
                        className="text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 px-3 py-1.5 rounded"
                      >
                        Edit
                      </button>
                    </div>
                  </div>
                ))}
              {prompts.length === 0 && <p className="text-gray-500 text-sm">No prompts found.</p>}
            </div>
          )}
        </div>
      )}

      {section === 'settings' && (
        <>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setSettingsMode('basic')}
              className={`text-xs px-3 py-1.5 rounded ${
                settingsMode === 'basic' ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-300'
              }`}
            >
              Basic
            </button>
            <button
              type="button"
              onClick={() => setSettingsMode('advanced')}
              className={`text-xs px-3 py-1.5 rounded ${
                settingsMode === 'advanced' ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-300'
              }`}
            >
              Advanced
            </button>
            <span className={`text-xs ml-2 ${settingsGlobalStatus.tone}`}>
              {settingsGlobalStatus.label}
            </span>
          </div>

          {settingsMode === 'advanced' && (
            <>
              <div className="flex flex-wrap gap-2">
                {CATEGORIES.map(c => (
                  <button
                    key={c}
                    type="button"
                    onClick={() => setCat(c)}
                    className={`text-sm px-4 py-1.5 rounded-full transition-colors ${
                      cat === c ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-400 hover:text-white'
                    }`}
                  >
                    {c}
                  </button>
                ))}
              </div>
              <div className="bg-gray-900/40 border border-gray-800 rounded-lg p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    type="text"
                    placeholder="Search by key..."
                    value={settingsSearch}
                    onChange={e => setSettingsSearch(e.target.value)}
                    autoComplete="off"
                    autoCorrect="off"
                    spellCheck={false}
                    name="settings-search"
                    className="ml-auto bg-gray-900 border border-gray-700 rounded px-3 py-1.5 text-xs text-gray-200 outline-none focus:border-indigo-500 w-72 max-w-full"
                  />
                </div>
              </div>
            </>
          )}

          {isLoading ? (
            <TableSkeleton rows={6} columns={3} />
          ) : settingsError ? (
            <ErrorState message="Failed to load settings." onRetry={() => refetchSettings()} />
          ) : (
            <div className="space-y-3">
              {settingsMode === 'basic' ? (
                <>
                  {basicRowsByCategory.map(group => (
                    <div key={group.category} className="space-y-2">
                      <p className="text-xs uppercase tracking-wide text-gray-500">{group.category}</p>
                      {group.rows.map((s: any) => (
                        <SettingField
                          key={`${group.category}:${s.key}`}
                          cat={group.category}
                          setting={s}
                          onNotify={pushToast}
                          onStatusChange={handleStatusChange}
                          onSave={() => {
                            qc.invalidateQueries({ queryKey: ['settings'] })
                            if (group.category === 'scheduler') {
                              qc.invalidateQueries({ queryKey: ['scheduler'] })
                            }
                          }}
                        />
                      ))}
                    </div>
                  ))}
                  {basicRowsByCategory.length === 0 && <p className="text-gray-500 text-sm">No basic settings found.</p>}
                </>
              ) : (
                <>
                  {visibleSettings.length === 0 && (
                    <p className="text-gray-500 text-sm">No settings matched your filters.</p>
                  )}
                  {visibleSettings.map((s: any) => (
                    <SettingField
                      key={`${cat}:${s.key}`}
                      cat={cat}
                      setting={s}
                      onNotify={pushToast}
                      onStatusChange={handleStatusChange}
                      onSave={() => {
                        qc.invalidateQueries({ queryKey: ['settings'] })
                        if (cat === 'scheduler') {
                          qc.invalidateQueries({ queryKey: ['scheduler'] })
                        }
                      }}
                    />
                  ))}
                </>
              )}
            </div>
          )}

        </>
      )}

      {section === 'token_usage' && (
        <div className="space-y-4">
          {tokensLoading && <LoadingState label="Loading token usage..." />}
          {tokensError && (
            <ErrorState message="Failed to load token usage." onRetry={() => refetchTokenStats()} />
          )}
          <div className="border border-gray-800 rounded-xl p-4 space-y-3 bg-gray-900/40">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <h3 className="text-sm font-semibold text-gray-200">Token Usage</h3>
              <div className="flex gap-1">
                {(['today', '7d', '30d', 'all'] as const).map(p => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setTokenPeriod(p)}
                    className={`text-xs px-2.5 py-1 rounded ${tokenPeriod === p ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-300'}`}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              <div className="bg-gray-800/70 rounded p-2"><span className="text-gray-500">Calls</span><p className="text-gray-200 mt-1">{tokenStats?.totals?.calls ?? '—'}</p></div>
              <div className="bg-gray-800/70 rounded p-2"><span className="text-gray-500">Retried</span><p className="text-gray-200 mt-1">{tokenStats?.totals?.retried_calls ?? '—'}</p></div>
              <div className="bg-gray-800/70 rounded p-2"><span className="text-gray-500">Errors</span><p className="text-gray-200 mt-1">{tokenStats?.totals?.calls_with_errors ?? '—'}</p></div>
              <div className="bg-gray-800/70 rounded p-2"><span className="text-gray-500">Cost</span><p className="text-gray-200 mt-1">{fmtUsd(tokenStats?.totals?.cost_usd)}</p></div>
              <div className="bg-gray-800/70 rounded p-2"><span className="text-gray-500">Input</span><p className="text-gray-200 mt-1">{fmtTokens(tokenStats?.totals?.input_tokens)}</p></div>
              <div className="bg-gray-800/70 rounded p-2"><span className="text-gray-500">Output</span><p className="text-gray-200 mt-1">{fmtTokens(tokenStats?.totals?.output_tokens)}</p></div>
              <div className="bg-gray-800/70 rounded p-2"><span className="text-gray-500">Duration</span><p className="text-gray-200 mt-1">{tokenStats?.totals?.duration_seconds != null ? `${tokenStats.totals.duration_seconds.toFixed(1)}s` : '—'}</p></div>
              <div className="bg-gray-800/70 rounded p-2"><span className="text-gray-500">Avg call</span><p className="text-gray-200 mt-1">{tokenStats?.totals?.avg_duration_seconds != null ? `${tokenStats.totals.avg_duration_seconds.toFixed(2)}s` : '—'}</p></div>
            </div>
          </div>

          <div className="space-y-4">
            <UsageTable
              title="By agent (stage + model)"
              rows={tokenStats?.by_stage_model ?? []}
              columns={[
                { key: 'stage', label: 'Agent/stage' },
                { key: 'provider_model', label: 'Model', render: (r: any) => `${r.provider}/${r.model}` },
                { key: 'calls', label: 'Calls', align: 'right' },
                { key: 'retried', label: 'Retried', align: 'right' },
                { key: 'errors', label: 'Errors', align: 'right' },
                { key: 'input_tokens', label: 'Input', align: 'right', render: (r: any) => fmtTokens(r.input_tokens) },
                { key: 'output_tokens', label: 'Output', align: 'right', render: (r: any) => fmtTokens(r.output_tokens) },
                { key: 'cost_usd', label: 'Cost', align: 'right', render: (r: any) => fmtUsd(r.cost_usd) },
                { key: 'avg_duration_seconds', label: 'Avg sec', align: 'right', render: (r: any) => r.avg_duration_seconds?.toFixed?.(2) ?? '—' },
              ]}
            />
            <UsageTable
              title="By stage"
              rows={tokenStats?.by_stage ?? []}
              columns={[
                { key: 'stage', label: 'Stage' },
                { key: 'calls', label: 'Calls', align: 'right' },
                { key: 'retried', label: 'Retried', align: 'right' },
                { key: 'errors', label: 'Errors', align: 'right' },
                { key: 'input_tokens', label: 'Input', align: 'right', render: (r: any) => fmtTokens(r.input_tokens) },
                { key: 'output_tokens', label: 'Output', align: 'right', render: (r: any) => fmtTokens(r.output_tokens) },
                { key: 'cost_usd', label: 'Cost', align: 'right', render: (r: any) => fmtUsd(r.cost_usd) },
              ]}
            />
            <UsageTable
              title="By model"
              rows={tokenStats?.by_model ?? []}
              columns={[
                { key: 'provider_model', label: 'Model', render: (r: any) => `${r.provider}/${r.model}` },
                { key: 'calls', label: 'Calls', align: 'right' },
                { key: 'retried', label: 'Retried', align: 'right' },
                { key: 'errors', label: 'Errors', align: 'right' },
                { key: 'cost_usd', label: 'Cost', align: 'right', render: (r: any) => fmtUsd(r.cost_usd) },
                { key: 'avg_cost_per_call', label: 'Avg cost/call', align: 'right', render: (r: any) => fmtUsd(r.avg_cost_per_call) },
              ]}
            />
            <UsageTable
              title="Retry reasons"
              rows={tokenStats?.by_retry_reason ?? []}
              columns={[
                { key: 'retry_reason', label: 'Reason' },
                { key: 'calls', label: 'Calls', align: 'right' },
              ]}
            />
            <UsageTable
              title="Top runs by cost"
              rows={tokenStats?.by_run ?? []}
              columns={[
                { key: 'run_id', label: 'Run', render: (r: any) => String(r.run_id || '').slice(0, 8) },
                { key: 'status', label: 'Status' },
                { key: 'started_at', label: 'Started', render: (r: any) => fmtDate(r.started_at) },
                { key: 'calls', label: 'Calls', align: 'right' },
                { key: 'retried', label: 'Retried', align: 'right' },
                { key: 'errors', label: 'Errors', align: 'right' },
                { key: 'cost_usd', label: 'Cost', align: 'right', render: (r: any) => fmtUsd(r.cost_usd) },
              ]}
            />
          </div>
        </div>
      )}

      {section === 'maintenance' && (
        <div className="space-y-4">
          <div className="bg-gray-900/40 border border-gray-800 rounded-xl p-4 space-y-3">
            <h3 className="text-sm font-semibold text-gray-200">Runtime worker timings</h3>
            <p className="text-xs text-gray-500">
              Snapshot of timing-related settings currently applied to workers and scheduler.
            </p>
            {timingRows.length === 0 ? (
              <p className="text-xs text-gray-500">No timing keys found.</p>
            ) : (
              <div className="overflow-auto border border-gray-800 rounded-lg">
                <table className="w-full text-xs">
                  <thead className="bg-gray-900/70">
                    <tr>
                      <th className="text-left px-2 py-1.5 text-gray-500">Category</th>
                      <th className="text-left px-2 py-1.5 text-gray-500">Key</th>
                      <th className="text-left px-2 py-1.5 text-gray-500">Value</th>
                      <th className="text-left px-2 py-1.5 text-gray-500">Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    {timingRows.map(row => (
                      <tr key={`${row.category}:${row.key}`} className="border-t border-gray-800">
                        <td className="px-2 py-1.5 text-gray-300">{row.category}</td>
                        <td className="px-2 py-1.5 text-gray-200 font-mono">{row.key}</td>
                        <td className="px-2 py-1.5 text-gray-300 font-mono">{typeof row.value === 'object' ? JSON.stringify(row.value) : String(row.value)}</td>
                        <td className="px-2 py-1.5 text-gray-500">{row.description || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="bg-gray-900/40 border border-gray-800 rounded-xl p-4 space-y-3">
            <h3 className="text-sm font-semibold text-gray-200">Polymarket CLOB health</h3>
            <p className="text-xs text-gray-500">
              Checks live CLOB connectivity from backend using configured credentials. Use this before live submit to
              detect route/VPN instability.
            </p>
            <button
              type="button"
              onClick={() => void handlePolymarketClobHealthCheck()}
              disabled={clobHealthLoading}
              className="text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 px-3 py-2 rounded-lg disabled:opacity-60"
            >
              {clobHealthLoading ? 'Checking…' : 'Run CLOB health check'}
            </button>
            {clobHealthError && <p className="text-xs text-red-400">{clobHealthError}</p>}
            {clobHealthResult && (
              <div
                className={`text-xs rounded-lg border px-3 py-2 space-y-1 ${
                  clobHealthResult.ok
                    ? 'border-emerald-800/80 bg-emerald-950/25 text-emerald-100'
                    : 'border-red-800/80 bg-red-950/30 text-red-100'
                }`}
              >
                <p className="font-medium">{clobHealthResult.ok ? 'CLOB reachable' : 'CLOB check failed'}</p>
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-gray-300 font-mono">
                  <dt className="text-gray-500">Latency</dt>
                  <dd>{clobHealthResult.latency_ms} ms</dd>
                  <dt className="text-gray-500">Balance payload</dt>
                  <dd>{clobHealthResult.has_balance_payload ? 'yes' : 'no'}</dd>
                  {clobHealthResult.wallet_address != null && clobHealthResult.wallet_address !== '' && (
                    <>
                      <dt className="text-gray-500">Wallet</dt>
                      <dd>{clobHealthResult.wallet_address}</dd>
                    </>
                  )}
                </dl>
              </div>
            )}
          </div>

          <div className="bg-gray-900/40 border border-gray-800 rounded-xl p-4 space-y-3">
            <h3 className="text-sm font-semibold text-gray-200">Polymarket server geoblock</h3>
            <p className="text-xs text-gray-500">
              Calls{' '}
              <code className="text-gray-400">https://polymarket.com/api/geoblock</code> from this
              application&apos;s backend — the same egress IP used for live CLOB requests. This is not your
              browser IP.
            </p>
            <button
              type="button"
              onClick={() => void handlePolymarketGeoblockCheck()}
              disabled={geoblockLoading}
              className="text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 px-3 py-2 rounded-lg disabled:opacity-60"
            >
              {geoblockLoading ? 'Checking…' : 'Check from backend'}
            </button>
            {geoblockError && <p className="text-xs text-red-400">{geoblockError}</p>}
            {geoblockResult && (
              <div
                className={`text-xs rounded-lg border px-3 py-2 space-y-1 ${
                  geoblockResult.blocked
                    ? 'border-red-800/80 bg-red-950/30 text-red-100'
                    : 'border-emerald-800/80 bg-emerald-950/25 text-emerald-100'
                }`}
              >
                <p className="font-medium">
                  {geoblockResult.blocked ? 'Blocked for trading' : 'Not blocked'}
                </p>
                <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-gray-300 font-mono">
                  {geoblockResult.ip != null && geoblockResult.ip !== '' && (
                    <>
                      <dt className="text-gray-500">IP</dt>
                      <dd>{geoblockResult.ip}</dd>
                    </>
                  )}
                  {geoblockResult.country != null && geoblockResult.country !== '' && (
                    <>
                      <dt className="text-gray-500">Country</dt>
                      <dd>{geoblockResult.country}</dd>
                    </>
                  )}
                  {geoblockResult.region != null && geoblockResult.region !== '' && (
                    <>
                      <dt className="text-gray-500">Region</dt>
                      <dd>{geoblockResult.region}</dd>
                    </>
                  )}
                </dl>
              </div>
            )}
          </div>

          <div className="bg-gray-900/40 border border-gray-800 rounded-xl p-4 space-y-3">
            <h3 className="text-sm font-semibold text-gray-200">Safe reset actions</h3>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void handleReset()}
                disabled={resetting}
                className="bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm px-3 py-2 rounded-lg border border-gray-700"
              >
                {resetting ? 'Resetting…' : 'Reset settings to defaults'}
              </button>
              <button
                type="button"
                onClick={() => void handleResetPrompts()}
                disabled={resettingPrompts}
                className="text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 px-3 py-2 rounded-lg"
              >
                {resettingPrompts ? '…' : 'Reset prompts to defaults'}
              </button>
              <button
                type="button"
                onClick={() => void handleManualSettlementSync()}
                disabled={syncingSettlements}
                className="text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-300 px-3 py-2 rounded-lg"
              >
                {syncingSettlements ? 'Syncing…' : 'Sync settlements (fallback)'}
              </button>
            </div>
          </div>

          <div className="bg-red-950/40 border border-red-900 rounded-xl p-4 space-y-3">
            <h3 className="text-sm font-semibold text-red-200">Danger zone</h3>
            <p className="text-xs text-red-300/80">
              Deletes runtime history and statistics (bets, runs, analyses, LLM calls, market snapshots, wallet snapshots, markets).
              Settings and prompts are preserved.
            </p>
            <button
              type="button"
              onClick={() => void handleRuntimeReset()}
              disabled={runtimeResetting}
              className="text-xs bg-red-700 hover:bg-red-600 disabled:opacity-60 text-white px-3 py-2 rounded-lg border border-red-500"
            >
              {runtimeResetting ? 'Resetting runtime…' : 'Clear history and runtime statistics'}
            </button>
          </div>
        </div>
      )}
      {activePrompt && (
        <PromptEditorModal
          row={activePrompt}
          onClose={() => setActivePrompt(null)}
          onSaved={() => qc.invalidateQueries({ queryKey: ['prompts'] })}
          onNotify={pushToast}
        />
      )}
    </div>
  )
}

function UsageTable({
  title,
  rows,
  columns,
}: {
  title: string
  rows: any[]
  columns: Array<{ key: string; label: string; align?: 'left' | 'right'; render?: (row: any) => any }>
}) {
  return (
    <div className="bg-gray-900/40 border border-gray-800 rounded-xl p-4 space-y-2">
      <h4 className="text-sm text-gray-200 font-semibold">{title}</h4>
      {rows.length === 0 ? (
        <p className="text-xs text-gray-500">No data for selected period.</p>
      ) : (
        <div className="overflow-auto border border-gray-800 rounded-lg">
          <table className="w-full text-xs min-w-[780px]">
            <thead className="bg-gray-900/70">
              <tr>
                {columns.map(col => (
                  <th
                    key={col.key}
                    className={`px-2 py-1.5 text-gray-500 ${col.align === 'right' ? 'text-right' : 'text-left'}`}
                  >
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, idx) => (
                <tr key={`${title}:${idx}`} className="border-t border-gray-800">
                  {columns.map(col => (
                    <td
                      key={col.key}
                      className={`px-2 py-1.5 text-gray-300 ${col.align === 'right' ? 'text-right font-mono' : 'text-left'}`}
                    >
                      {col.render ? col.render(row) : (row[col.key] ?? '—')}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
