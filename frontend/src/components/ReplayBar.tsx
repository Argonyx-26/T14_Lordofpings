import { Pause, Play, RotateCcw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { levelOf, localTime, post, rankIncidents } from '../lib'
import type { Clock, Incident, SiteConfigView } from '../types'
import { StatusSymbol } from './Symbols'

interface Props {
  clock: Clock | null
  config: SiteConfigView | null
  incidents: Incident[]
  mock: boolean
  onSelect: (id: string) => void
}

const SPEEDS = [1, 5, 10, 20, 30]

/**
 * Replay transport. The recorded window is a timeline: click anywhere to jump, diamonds are the staged scenarios,
 * coloured marks are incidents at the moment their first signal arrived. Space plays or pauses.
 */
export function ReplayBar({ clock, config, incidents, mock, onSelect }: Props) {
  const control = (cmd: string, value?: number) => !mock && post('/api/replay', { cmd, value }).catch(console.error)
  const track = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<number | null>(null)
  const span = clock ? clock.end_t - clock.start_t : 1
  const pct = (t: number) => (clock ? Math.min(100, Math.max(0, ((t - clock.start_t) / span) * 100)) : 0)
  const timeAt = (clientX: number) => {
    const r = track.current!.getBoundingClientRect()
    return clock!.start_t + Math.min(1, Math.max(0, (clientX - r.left) / r.width)) * span
  }
  const cfg = config ?? undefined

  const playing = !!clock?.playing
  const toggleRef = useRef(() => {})
  useEffect(() => { toggleRef.current = () => { if (!mock) post('/api/replay', { cmd: playing ? 'pause' : 'play' }).catch(console.error) } })
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.code !== 'Space' || e.target !== document.body) return
      e.preventDefault()
      toggleRef.current()
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [])

  return (
    <div className="flex h-11 shrink-0 items-center gap-4 px-4 hairline-b">
      <div className="flex items-center gap-1.5">
        <button className="btn btn-primary btn-icon" disabled={mock} aria-label={playing ? 'Pause' : 'Play'}
          title={`${playing ? 'Pause' : 'Play'} (space)`} onClick={() => control(playing ? 'pause' : 'play')}>
          {playing ? <Pause size={14} strokeWidth={2.2} /> : <Play size={14} strokeWidth={2.2} />}
        </button>
        <button className="btn btn-ghost btn-icon" disabled={mock} title="Back to the start" aria-label="Reset" onClick={() => control('reset')}>
          <RotateCcw size={14} strokeWidth={1.75} />
        </button>
        <div className="seg num hidden sm:inline-flex" aria-label="Replay speed">
          {SPEEDS.map((s) => (
            <button key={s} disabled={mock} data-on={clock?.speed === s} onClick={() => control('speed', s)}>{s}×</button>
          ))}
        </div>
      </div>

      {/* timeline */}
      <div ref={track} role="slider" aria-label="Replay position" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(clock ? pct(clock.sim_t) : 0)}
        className="group relative flex h-8 min-w-24 flex-1 cursor-pointer items-center"
        onMouseMove={(e) => clock && setHover(timeAt(e.clientX))} onMouseLeave={() => setHover(null)}
        onClick={(e) => clock && control('seek', timeAt(e.clientX))}>
        <div className="absolute inset-x-0 h-[3px] rounded-full bg-[var(--color-surface-3)]" />
        <div className="absolute left-0 h-[3px] rounded-full bg-[var(--color-fg-3)]" style={{ width: `${clock ? pct(clock.sim_t) : 0}%` }} />
        {hover !== null && (
          <span className="pointer-events-none absolute -top-0.5 z-10 -translate-x-1/2 rounded bg-[var(--color-surface-4)] px-1.5 py-px text-[10.5px] text-[var(--color-fg)]"
            style={{ left: `${pct(hover)}%` }}>
            <span className="num">{localTime(hover)}</span>
          </span>
        )}
        {config?.bookmarks.map((b) => (
          <button key={b.t + b.label} onClick={(e) => { e.stopPropagation(); control('seek', b.t) }} aria-label={`Jump to ${b.label}`}
            className="group/b absolute -translate-x-1/2 p-1" style={{ left: `${pct(b.t)}%` }}>
            <span className="block h-2 w-2 rotate-45 border border-[var(--color-fg-3)] bg-[var(--color-bg)] transition group-hover/b:border-[var(--color-fg)] group-hover/b:bg-[var(--color-fg)]" />
            <span className="pointer-events-none absolute left-1/2 top-6 z-20 hidden -translate-x-1/2 whitespace-nowrap rounded-md bg-[var(--color-surface-4)] px-2 py-1 text-[11px] text-[var(--color-fg)] shadow-lg group-hover/b:block">
              {b.label} <span className="num text-[var(--color-fg-3)]">{localTime(b.t)}</span>
            </span>
          </button>
        ))}
        {rankIncidents(incidents).map((i) => (
          <button key={i.incident_id} onClick={(e) => { e.stopPropagation(); onSelect(i.incident_id) }}
            title={`${i.incident_id} · ${i.title.split(' — ')[0]} · ${localTime(i.first_signal_at)}`}
            className="absolute bottom-0 -translate-x-1/2 p-0.5" style={{ left: `${pct(i.first_signal_at)}%` }}>
            <StatusSymbol level={i.status === 'watch' ? 'watch' : levelOf(i.score, cfg)} size={8} />
          </button>
        ))}
        {clock && <div className="pointer-events-none absolute h-4 w-[2px] -translate-x-1/2 rounded-full bg-[var(--color-fg)]" style={{ left: `${pct(clock.sim_t)}%` }} />}
      </div>

      <div className="flex items-center gap-3">
        <div className="flex flex-col items-end leading-none">
          <span className="num text-[20px] font-medium text-[var(--color-fg)]">{clock?.local.slice(11) ?? '--:--:--'}</span>
          <span className="mt-1 flex items-center gap-1.5 text-[10.5px] text-[var(--color-fg-3)]">
            <span className={`h-1.5 w-1.5 rounded-full ${playing ? 'bg-[var(--color-crit)] breathe' : 'bg-[var(--color-fg-4)]'}`} />
            {clock ? <>{playing ? `Replaying ${clock.speed}×` : clock.finished ? 'End of recording' : 'Paused'}<span className="hidden sm:inline"> · {clock.local.slice(0, 10)} site time</span></> : '—'}
          </span>
        </div>
      </div>
    </div>
  )
}
