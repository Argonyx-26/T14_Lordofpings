import { ArrowUpRight, Check, ChevronDown, CornerDownRight, LoaderCircle, ShieldAlert, Siren, X } from 'lucide-react'
import { useEffect, useRef, useState, type ComponentType } from 'react'
import { STATUS_LABEL } from '../lib'
import type { Incident, SiteConfigView } from '../types'

export type Action = 'ack' | 'escalate' | 'dismiss'

interface Choice {
  key: string
  label: string
  detail: string
  action: Action
  note: string
  Icon: ComponentType<{ size?: number; strokeWidth?: number; className?: string }>
  recommended?: boolean
  supervisorOnly?: boolean
}

/** Playbook actions that hand the incident up the chain rather than handling it on site. */
const ESCALATING = new Set(['notify_police'])

/**
 * The human decision, one menu. Every choice is one of the three things the backend records (acknowledge,
 * escalate, dismiss); the specific response is logged with it as a note in the hash-chained audit log.
 */
export function ResponseMenu({ incident, config, disabled, disabledReason, onAct, role = 'duty_officer' }: {
  incident: Incident
  role?: 'duty_officer' | 'supervisor'
  config: SiteConfigView | null
  disabled: boolean
  disabledReason?: string
  onAct: (action: Action, note: string) => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const root = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const close = (e: MouseEvent) => { if (root.current && !root.current.contains(e.target as Node)) setOpen(false) }
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    window.addEventListener('mousedown', close)
    window.addEventListener('keydown', esc)
    return () => { window.removeEventListener('mousedown', close); window.removeEventListener('keydown', esc) }
  }, [])

  const playbook = config?.playbook ?? {}
  const rec = incident.brief?.action_id
  const choices: Choice[] = []
  if (rec && rec !== 'monitor' && playbook[rec]) {
    const up = ESCALATING.has(rec)
    choices.push({ key: rec, label: playbook[rec], detail: `Recommended by ARGUS · marks it ${up ? 'escalated' : 'acknowledged'}`,
      action: up ? 'escalate' : 'ack', note: rec, Icon: CornerDownRight, recommended: true })
  }
  choices.push({ key: 'ack', label: 'Acknowledge', detail: "I've seen it and I'm handling it", action: 'ack', note: '', Icon: Check })
  if (rec !== 'dispatch_guard' && playbook.dispatch_guard) {
    choices.push({ key: 'dispatch_guard', label: playbook.dispatch_guard, detail: 'Marks it acknowledged and logs the dispatch', action: 'ack', note: 'dispatch_guard', Icon: ShieldAlert })
  }
  choices.push({ key: 'escalate', label: 'Escalate to a supervisor', detail: 'Hands the decision up the chain', action: 'escalate', note: '', Icon: ArrowUpRight })
  if (rec !== 'notify_police' && playbook.notify_police) {
    choices.push({ key: 'notify_police', label: playbook.notify_police, detail: 'Marks it escalated and logs the call', action: 'escalate', note: 'notify_police', Icon: Siren })
  }
  choices.push({ key: 'dismiss', label: 'Dismiss as a false alarm', detail: 'Closes it. Similar alerts in this area will score lower', action: 'dismiss', note: 'false_alarm', Icon: X })
  // Supervisor-only (the backend enforces it too): dismissing changes scoring policy, calling the police commits
  // outside resources. A duty officer sees them, greyed, and escalates instead.
  for (const c of choices) c.supervisorOnly = c.action === 'dismiss' || c.note === 'notify_police'

  const choose = async (c: Choice) => {
    setBusy(c.key)
    setError(null)
    try {
      await onAct(c.action, c.note)
      setOpen(false)
    } catch {
      setError('Could not record that. Is the backend running?')
    } finally {
      setBusy(null)
    }
  }

  const undecided = incident.status === 'open' || incident.status === 'watch'
  return (
    <div ref={root} className="relative flex-1">
      {open && (
        <div role="menu" className="pop absolute inset-x-0 bottom-full z-40 mb-2 overflow-hidden rounded-xl py-1.5"
          style={{ background: 'var(--color-surface-2)', boxShadow: '0 -12px 44px rgb(0 0 0 / .55), inset 0 0 0 1px var(--color-hair-2)' }}>
          {choices.map((c, k) => (
            <div key={c.key}>
              {k > 0 && choices[k - 1].recommended && <div className="mx-3 my-1.5 hairline-t" />}
              {c.key === 'dismiss' && <div className="mx-3 my-1.5 hairline-t" />}
              <button role="menuitem" onClick={() => choose(c)} disabled={!!busy || (c.supervisorOnly && role !== 'supervisor')}
                title={c.supervisorOnly && role !== 'supervisor' ? 'Supervisor only: escalate it to them' : undefined}
                className="flex w-full items-start gap-3 px-3.5 py-2 text-left transition hover:bg-[var(--color-surface-3)] disabled:opacity-60">
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md"
                  style={{ background: c.recommended ? 'var(--color-fg)' : 'var(--color-surface-4)', color: c.recommended ? '#0a0c0f' : c.key === 'dismiss' ? 'var(--color-fg-2)' : 'var(--color-fg)' }}>
                  {busy === c.key ? <LoaderCircle size={12} className="animate-spin" /> : <c.Icon size={12} strokeWidth={2.2} />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[13px] text-[var(--color-fg)]">{c.label}</span>
                  {c.supervisorOnly && <span className="float-right ml-2 text-[10px] uppercase tracking-wide text-[var(--color-fg-4)]">Supervisor</span>}
                  <span className="block text-[11px] text-[var(--color-fg-3)]">{c.detail}</span>
                </span>
                {incident.status === (c.action === 'ack' ? 'ack' : c.action === 'escalate' ? 'escalated' : 'dismissed') && !c.note && (
                  <span className="chip mt-0.5">current</span>
                )}
              </button>
            </div>
          ))}
        </div>
      )}
      <button onClick={() => setOpen(!open)} disabled={disabled} aria-haspopup="menu" aria-expanded={open}
        title={disabled ? disabledReason : 'Record what you decide; every choice goes in the audit log'}
        className={`btn w-full justify-center ${undecided ? 'btn-primary' : ''}`} style={{ height: 36 }}>
        {undecided ? 'Respond' : `${STATUS_LABEL[incident.status]} · change`}
        <ChevronDown size={14} strokeWidth={2} className={`transition ${open ? 'rotate-180' : ''}`} />
      </button>
      {error && <p className="mt-1.5 text-[11.5px] text-[var(--color-crit)]">{error}</p>}
    </div>
  )
}
