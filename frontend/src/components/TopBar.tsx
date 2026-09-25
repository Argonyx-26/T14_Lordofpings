import { post } from '../lib'
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
  const progress = clock ? (clock.sim_t - clock.start_t) / (clock.end_t - clock.start_t) : 0

  return (
    <header className="panel flex items-center gap-5 px-4 py-2.5">
      <div className="flex items-baseline gap-2">
        <span className="text-lg font-bold tracking-[0.2em] text-[var(--color-accent)]">ARGUS</span>
        <span className="text-xs text-[var(--color-mute)]">{config?.site_name ?? '…'}</span>
      </div>

      <div className="flex items-center gap-3">
        <div className="num text-2xl font-semibold">{clock?.local.slice(11) ?? '--:--:--'}</div>
        <div className="text-xs text-[var(--color-mute)]">{clock?.local.slice(0, 10)} · replay</div>
      </div>

      <div className="flex items-center gap-1.5">
        <button className="rounded-md bg-[var(--color-panel-2)] px-3 py-1.5 text-sm hover:bg-[var(--color-line)]"
          onClick={() => control(clock?.playing ? 'pause' : 'play')}>
          {clock?.playing ? '❚❚ Pause' : '▶ Play'}
        </button>
        <select className="rounded-md bg-[var(--color-panel-2)] px-2 py-1.5 text-sm" value={clock?.speed ?? 10}
          onChange={(e) => control('speed', Number(e.target.value))}>
          {SPEEDS.map((s) => <option key={s} value={s}>{s}×</option>)}
        </select>
        <select className="max-w-52 rounded-md bg-[var(--color-panel-2)] px-2 py-1.5 text-sm" value=""
          onChange={(e) => e.target.value && control('seek', Number(e.target.value))}>
          <option value="">Jump to…</option>
          {config?.bookmarks.map((b) => <option key={b.t + b.label} value={b.t}>{b.label}</option>)}
        </select>
        <button className="rounded-md px-2 py-1.5 text-sm text-[var(--color-mute)] hover:text-[var(--color-ink)]"
          onClick={() => control('reset')}>Reset</button>
      </div>

      <div className="h-1.5 flex-1 overflow-hidden rounded bg-[var(--color-panel-2)]">
        <div className="h-full bg-[var(--color-accent)]" style={{ width: `${Math.min(100, progress * 100)}%` }} />
      </div>

      <div className="flex items-center gap-2 text-xs">
        <span className="label">Role</span>
        {(['duty_officer', 'supervisor'] as Role[]).map((r) => (
          <button key={r} onClick={() => onRole(r)}
            className={`rounded px-2 py-1 ${role === r ? 'bg-[var(--color-accent)] text-black' : 'bg-[var(--color-panel-2)]'}`}>
            {r === 'duty_officer' ? 'Duty officer' : 'Supervisor'}
          </button>
        ))}
      </div>

      {mock ? (
        <span className="rounded bg-[var(--color-high)] px-2 py-1 text-xs font-bold text-black">MOCK DATA</span>
      ) : (
        <span className={`flex items-center gap-1.5 text-xs ${connected ? 'text-[var(--color-ok)]' : 'text-[var(--color-crit)]'}`}>
          <span className="h-2 w-2 rounded-full bg-current" /> {connected ? 'live' : 'offline'}
        </span>
      )}
    </header>
  )
}
