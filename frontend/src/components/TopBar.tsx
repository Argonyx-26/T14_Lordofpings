import { Pause, Play, RotateCcw } from 'lucide-react'
import { localTime, post } from '../lib'
import type { Clock, SiteConfigView } from '../types'

export type Role = 'duty_officer' | 'supervisor'

interface Props {
  clock: Clock | null
  config: SiteConfigView | null
  connected: boolean
  mock: boolean
  role: Role
  onRole: (r: Role) => void
}

const SPEEDS = [1, 5, 10, 20, 30]

export function TopBar({ clock, config, connected, mock, role, onRole }: Props) {
  const control = (cmd: string, value?: number) => !mock && post('/api/replay', { cmd, value }).catch(console.error)
  const span = clock ? clock.end_t - clock.start_t : 1
  const pct = (t: number) => (clock ? Math.min(100, Math.max(0, ((t - clock.start_t) / span) * 100)) : 0)

  return (
    <header className="flex h-14 shrink-0 items-center gap-6 px-5 hairline-b">
      <div className="flex items-baseline gap-3">
        <span className="display text-[28px] text-[var(--color-fg)]">Argus</span>
        <span className="hidden text-[11px] text-[var(--color-fg-3)] xl:inline">Situational awareness · {config?.site_name ?? '—'}</span>
      </div>

      <div className="flex items-center gap-2">
        <button className="btn btn-icon" title="Reset to start" onClick={() => control('reset')}><RotateCcw size={14} strokeWidth={1.75} /></button>
        <button className="btn btn-primary btn-icon" title={clock?.playing ? 'Pause' : 'Play'} onClick={() => control(clock?.playing ? 'pause' : 'play')}>
          {clock?.playing ? <Pause size={14} strokeWidth={2} /> : <Play size={14} strokeWidth={2} />}
        </button>
        <div className="seg num">
          {SPEEDS.map((s) => (
            <button key={s} data-on={clock?.speed === s} onClick={() => control('speed', s)}>{s}×</button>
          ))}
        </div>
      </div>

      {/* Timeline: progress through the replay window, with the staged scenarios as clickable markers */}
      <div className="relative flex h-8 min-w-40 flex-1 items-center">
        <div className="absolute inset-x-0 h-px bg-[var(--color-hair-2)]" />
        <div className="absolute left-0 h-px bg-[var(--color-fg-2)]" style={{ width: `${clock ? pct(clock.sim_t) : 0}%` }} />
        {clock && <div className="absolute h-3 w-px bg-[var(--color-fg)]" style={{ left: `${pct(clock.sim_t)}%` }} />}
        {config?.bookmarks.map((b) => (
          <button key={b.t + b.label} onClick={() => control('seek', b.t)} title={`${b.label} · ${localTime(b.t)}`}
            className="group absolute -translate-x-1/2" style={{ left: `${pct(b.t)}%` }}>
            <span className="block h-2 w-2 rotate-45 border border-[var(--color-fg-3)] bg-[var(--color-bg)] transition group-hover:border-[var(--color-fg)] group-hover:bg-[var(--color-fg)]" />
            <span className="pointer-events-none absolute left-1/2 top-4 hidden -translate-x-1/2 whitespace-nowrap rounded bg-[var(--color-surface-3)] px-2 py-1 text-[11px] text-[var(--color-fg)] shadow-lg group-hover:block">
              {b.label} <span className="num text-[var(--color-fg-3)]">{localTime(b.t)}</span>
            </span>
          </button>
        ))}
      </div>

      <div className="flex flex-col items-end leading-none">
        <span className="num text-[22px] font-medium text-[var(--color-fg)]">{clock?.local.slice(11) ?? '--:--:--'}</span>
        <span className="mt-1 text-[10.5px] text-[var(--color-fg-3)]">{clock ? `${clock.local.slice(0, 10)} · site time · replay` : '—'}</span>
      </div>

      <div className="seg">
        {(['duty_officer', 'supervisor'] as Role[]).map((r) => (
          <button key={r} data-on={role === r} onClick={() => onRole(r)}>{r === 'duty_officer' ? 'Duty officer' : 'Supervisor'}</button>
        ))}
      </div>

      {mock ? (
        <span className="rounded-md border border-[var(--color-high)] px-2 py-1 text-[11px] font-medium text-[var(--color-high)]">Mock data</span>
      ) : (
        <span className="flex items-center gap-2 text-[11px] text-[var(--color-fg-2)]">
          <span className={`h-1.5 w-1.5 rounded-full ${connected ? 'bg-[var(--color-ok)]' : 'bg-[var(--color-crit)] breathe'}`} />
          {connected ? 'Connected' : 'Reconnecting'}
        </span>
      )}
    </header>
  )
}
