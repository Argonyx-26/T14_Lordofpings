import { ArrowLeft, Upload, LogOut } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { SOURCE_LABEL, fmt, post } from '../lib'
import type { SiteConfigView, Summary } from '../types'
import { SourceIcon } from './Symbols'

export type Role = 'duty_officer' | 'supervisor'

interface Props {
  config: SiteConfigView | null
  summary: Summary | null
  connected: boolean
  mock: boolean
  role: Role
  onRole: (r: Role) => void
  onAnalyse: () => void
  analysing: boolean
  ask: ReactNode
}

/** Global status bar: identity, the question box, stream health, link state and who is signed in. */
export function TopBar({ config, summary, connected, mock, role, onRole, onAnalyse, analysing, ask }: Props) {
  const sources = Object.entries(summary?.by_source ?? {})
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
          title="A real snapshot of the MEVA replay at 15:20, bundled with the page. Live footage, replay and uploads need the backend.">
          Offline demo · real snapshot
        </span>
      ) : (
        <span className="flex items-center gap-1.5 text-[11.5px] text-[var(--color-fg-2)]" role="status">
          <span className={`h-1.5 w-1.5 rounded-full ${connected ? 'bg-[var(--color-ok)]' : 'bg-[var(--color-crit)] breathe'}`} />
          <span className="hidden sm:inline">{connected ? 'Live link' : 'Reconnecting'}</span>
        </span>
      )}

      {!mock && config?.profiles && <ProfileSwitch config={config} role={role} />}

      <div className="seg hidden md:inline-flex" aria-label="Signed in as">
        {(['duty_officer', 'supervisor'] as Role[]).map((r) => (
          <button key={r} data-on={role === r} onClick={() => onRole(r)}
            title={r === 'supervisor' ? 'Can also dismiss false alarms, call the police and change how strict the site is'
              : 'Acknowledges, dispatches guards and escalates to a supervisor'}>
            {r === 'duty_officer' ? 'Duty officer' : 'Supervisor'}</button>
        ))}
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
