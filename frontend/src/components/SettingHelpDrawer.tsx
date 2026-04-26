import { CircleHelp } from 'lucide-react'
import type { SettingHelpDoc } from '../lib/settingsHelp'
import { getSettingHelp, settingHelpKey } from '../lib/settingsHelp'

export function SettingHelpTrigger({
  category,
  settingKey,
  serverDescription,
  onOpen,
}: {
  category: string
  settingKey: string
  serverDescription: string | null | undefined
  onOpen: () => void
}) {
  const extended = getSettingHelp(category, settingKey)
  const hasServer = !!(serverDescription && serverDescription.trim())
  if (!extended && !hasServer) return null

  return (
    <button
      type="button"
      onClick={e => {
        e.preventDefault()
        e.stopPropagation()
        onOpen()
      }}
      aria-label={`Help for ${category}.${settingKey}`}
      title="Explain this setting"
      className="shrink-0 inline-flex items-center justify-center rounded-md p-1 text-gray-500 hover:text-indigo-300 hover:bg-gray-800/80 border border-transparent hover:border-gray-700 transition-colors"
    >
      <CircleHelp className="w-3.5 h-3.5" strokeWidth={2} />
    </button>
  )
}

export function SettingHelpDrawer({
  open,
  onClose,
  category,
  settingKey,
  serverDescription,
}: {
  open: boolean
  onClose: () => void
  category: string
  settingKey: string
  serverDescription: string | null | undefined
}) {
  if (!open) return null

  const id = settingHelpKey(category, settingKey)
  const doc: SettingHelpDoc | undefined = getSettingHelp(category, settingKey)
  const hasServer = !!(serverDescription && serverDescription.trim())
  const paragraphs = doc?.details
    ? Array.isArray(doc.details)
      ? doc.details
      : [doc.details]
    : []

  return (
    <div
      className="fixed inset-0 z-[60] flex justify-end bg-black/60"
      role="dialog"
      aria-modal="true"
      aria-labelledby={`setting-help-title-${id}`}
      onClick={onClose}
    >
      <div
        className="h-full w-full max-w-md bg-panel border-l border-border shadow-2xl flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div className="min-w-0">
            <p id={`setting-help-title-${id}`} className="text-sm font-mono text-indigo-300 truncate">
              {category}.{settingKey}
            </p>
            {doc?.title && <p className="text-xs text-gray-400 mt-0.5">{doc.title}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-xs text-muted hover:text-white px-2 py-1 shrink-0"
          >
            Close
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4 text-sm text-gray-300">
          {doc?.warning && (
            <div className="rounded-lg border border-amber-800/60 bg-amber-950/25 px-3 py-2 text-amber-100/95 text-xs leading-relaxed">
              {doc.warning}
            </div>
          )}

          {paragraphs.length > 0 && (
            <div className="space-y-2">
              {paragraphs.map((p, i) => (
                <p key={i} className="text-xs text-gray-300 leading-relaxed">
                  {p}
                </p>
              ))}
            </div>
          )}

          {hasServer && (
            <div className="space-y-1.5">
              <p className="text-[10px] uppercase tracking-wide text-gray-500">Server description</p>
              <p className="text-xs text-gray-400 leading-relaxed whitespace-pre-wrap">{serverDescription}</p>
            </div>
          )}

          {doc?.related && doc.related.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-[10px] uppercase tracking-wide text-gray-500">Related settings</p>
              <ul className="text-xs space-y-1.5">
                {doc.related.map((r, i) => (
                  <li key={i} className="font-mono text-gray-400">
                    <span className="text-indigo-300/90">{r.category}</span>
                    <span className="text-gray-600">.</span>
                    <span className="text-gray-200">{r.key}</span>
                    {r.note ? <span className="text-gray-500 font-sans"> — {r.note}</span> : null}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {!doc && !hasServer && <p className="text-xs text-gray-500">No help text available.</p>}
        </div>
      </div>
    </div>
  )
}
