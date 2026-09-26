import { ArrowLeft, LogOut, ShieldCheck, Upload } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { API, SOURCE_LABEL, fmt, post, setSession } from '../lib'
import type { SiteConfigView, Summary } from '../types'
import { SourceIcon } from './Symbols'

export type Role = 'duty_officer' | 'supervisor'

interface Props {
  config: SiteConfigView | null
  summary: Summary | null
  connected: boolean
  mock: boolean
  placeholders?: number
  role: Role
  onRole: (r: Role) => void
  onAnalyse: () => void
  analysing: boolean
  ask: ReactNode
  onDesk?: () => void
}

/** Global status bar: identity, the question box, stream health, link state and who is signed in. */
export function TopBar({ config, summary, connected, mock, placeholders = 0, role, onRole, onAnalyse, analysing, ask, onDesk }: Props) {
  const sources = Object.entries(summary?.by_source ?? {})
  const [asking, setAsking] = useState(false)
  const [pin, setPin] = useState('')
  const [pinError, setPinError] = useState<string | null>(null)
  /** Sign in as a role. With a supervisor PIN set on the backend, the PIN is checked there before the switch. */
  const choose = async (r: Role) => {
    if (r === 'supervisor' && config?.supervisor_pin_required && !mock) { setAsking(true); setPinError(null); return }
    setSession(r); onRole(r)
  }
  const verify = async () => {
    const r = await fetch(API + '/api/role', { headers: { 'X-Argus-Role': 'supervisor', 'X-Argus-Pin': pin } }).catch(() => null)
    if (r?.ok) { setSession('supervisor', pin); onRole('supervisor'); setAsking(false); setPin('') }
    else setPinError(r?.status === 401 ? 'Wrong PIN' : 'Backend unreachable')
  }
  return (
    <header className="flex h-12 shrink-0 items-center gap-4 px-4 hairline-b" style={{ background: 'var(--color-surface)' }}>
      <div className="flex min-w-0 items-baseline gap-2.5">
        <span className="wordmark text-[26px] text-[var(--color-fg)]">Argus</span>
        <span className="hidden truncate text-[11.5px] text-[var(--color-fg-3)] md:inline">{config?.site_name ?? '—'}</span>
      </div>

      {!analysing && <div className="ml-auto w-full max-w-[300px] min-w-0 lg:ml-6">{ask}</div>}

      {/* stream health: every source reporting, and how much each has sent */}
      <div className="ml-auto hidden items-center gap-3.5 xl:flex" aria-label="Data streams">
        {sources.map(([src, n]) => (
          <span key={src} className="flex items-center gap-1.5 text-[11.5px]" title={`${SOURCE_LABEL[src] ?? src}: ${fmt(n)} signals so far`}>
            <SourceIcon source={src} />
            <span className="text-[var(--color-fg-3)]">{SOURCE_LABEL[src]?.split(' ')[0] ?? src}</span>
            <span className="num text-[var(--color-fg-2)]">{fmt(n)}</span>
          </span>
        ))}
      </div>

      <button className="btn btn-sm hidden sm:inline-flex" data-on={analysing} onClick={onAnalyse} disabled={mock}
        title="Upload any video and analyse it with the same detectors and fusion">
        {analysing ? <ArrowLeft size={13} strokeWidth={1.75} /> : <Upload size={13} strokeWidth={1.75} />}
        {analysing ? 'Back to console' : 'Analyse a video'}
      </button>

      {mock ? (
        <span className="chip" style={{ color: 'var(--color-watch)' }}
          title={placeholders
            ? `A snapshot of the MEVA replay at 15:20, bundled with the page. Doors and phone counts are real; ${placeholders} camera event${placeholders === 1 ? ' is a stand-in' : 's are stand-ins'} for the pipeline's detections, marked in the evidence. Live footage, replay and uploads need the backend.`
            : 'A real snapshot of the MEVA replay at 15:20, bundled with the page. Live footage, replay and uploads need the backend.'}>
          {placeholders ? `Offline demo · ${placeholders} placeholder event${placeholders === 1 ? '' : 's'}` : 'Offline demo · real snapshot'}
        </span>
      ) : (
        <span className="flex items-center gap-1.5 text-[11.5px] text-[var(--color-fg-2)]" role="status">
          <span className={`h-1.5 w-1.5 rounded-full ${connected ? 'bg-[var(--color-ok)]' : 'bg-[var(--color-crit)] breathe'}`} />
          <span className="hidden sm:inline">{connected ? 'Live link' : 'Reconnecting'}</span>
        </span>
      )}

      {!mock && config?.profiles && <ProfileSwitch config={config} role={role} />}

      {role === 'supervisor' && onDesk && (
        <button className="btn btn-sm" onClick={onDesk} title="The whole decision log, what ARGUS has learned from dismissals, and dismissed incidents">
          <ShieldCheck size={13} strokeWidth={1.75} /> <span className="hidden lg:inline">Supervisor desk</span>
        </button>
      )}

      <div className="relative hidden md:block">
        <div className="seg" aria-label="Signed in as">
          {(['duty_officer', 'supervisor'] as Role[]).map((r) => (
            <button key={r} data-on={role === r} onClick={() => choose(r)}
              title={r === 'supervisor'
                ? 'Oversight and policy: also dismisses false alarms, calls the police, changes how strict the site is, reopens dismissals, and sees detector internals, the whole decision log and what ARGUS has learned'
                : 'Runs the floor: acknowledges, dispatches guards, escalates; sees each incident\'s evidence in plain language and its own decisions'}>
              {r === 'duty_officer' ? 'Duty officer' : 'Supervisor'}</button>
          ))}
        </div>
        {asking && (
          <form className="pop absolute right-0 top-full z-50 mt-2 w-[220px] rounded-xl p-3" onSubmit={(e) => { e.preventDefault(); verify() }}
            style={{ background: 'var(--color-surface-2)', boxShadow: '0 18px 50px rgb(0 0 0 / .6), inset 0 0 0 1px var(--color-hair-2)' }}>
            <label className="eyebrow mb-1.5 block" htmlFor="sup-pin">Supervisor PIN</label>
            <input id="sup-pin" type="password" inputMode="numeric" autoFocus value={pin} onChange={(e) => setPin(e.target.value)}
              className="num h-8 w-full rounded-md bg-[var(--color-surface-3)] px-2.5 text-[13px] text-[var(--color-fg)] outline-none" style={{ boxShadow: 'inset 0 0 0 1px var(--color-hair-2)' }} />
            {pinError && <p className="mt-1.5 text-[11px] text-[var(--color-crit)]">{pinError}</p>}
            <div className="mt-2.5 flex justify-end gap-1.5">
              <button type="button" className="btn btn-sm btn-ghost" onClick={() => { setAsking(false); setPin('') }}>Cancel</button>
              <button type="submit" className="btn btn-sm btn-primary">Sign in</button>
            </div>
          </form>
        )}
      </div>

      <a className="btn btn-sm" href={homeHref()} title="Leave the demo and go back to the project's home page">
        <LogOut size={13} strokeWidth={1.75} /> <span className="hidden sm:inline">Exit demo</span>
      </a>
    </header>
  )
}

/** Security profile of the site (backend profiles.yaml): how strict ARGUS is. Switching re-scores the replay so far. */
function ProfileSwitch({ config, role }: { config: SiteConfigView; role: Role }) {
  const [busy, setBusy] = useState(false)
  const current = config.profile
  const allowed = role === 'supervisor'           // the backend refuses anyone else (403)
  const pick = async (id: string) => {
    if (id === current || busy || !allowed) return
    setBusy(true)
    try { await post('/api/profile', { name: id, role }) } finally { setBusy(false) }
  }
  return (
    <div className="seg hidden lg:inline-flex" aria-label="Security profile"
      title={allowed ? 'How strict ARGUS is at this site' : 'Only a supervisor can change how strict the site is'}>
      {config.profiles!.map((p) => (
        <button key={p.id} data-on={p.id === current} disabled={busy || (!allowed && p.id !== current)} onClick={() => pick(p.id)}
          title={allowed ? p.description : `${p.description} · supervisor only`}>
          {p.label}
        </button>
      ))}
    </div>
  )
}

/** The project's home page: next to the console when published (/console/ -> ../), /site/ on the demo laptop. */
function homeHref(): string {
  const path = typeof window !== 'undefined' ? window.location.pathname : '/'
  return path.includes('/console') ? '../' : '/site/'
}
