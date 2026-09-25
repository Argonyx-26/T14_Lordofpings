import { localTime, scoreColor, severityLabel } from '../lib'
import type { Incident, SiteConfigView } from '../types'

const ORDER: Record<string, number> = { open: 0, escalated: 0, ack: 1, watch: 2 }

export function IncidentQueue({ incidents, config, selected, onSelect }: {
  incidents: Incident[]; config: SiteConfigView | null; selected: string | null; onSelect: (id: string) => void
}) {
  const shown = incidents
    .filter((i) => i.status in ORDER)
    .sort((a, b) => ORDER[a.status] - ORDER[b.status] || b.score - a.score)
  const cfg = config ?? undefined

  return (
    <section className="surface flex min-h-0 min-w-0 flex-1 flex-col">
      <div className="flex h-10 shrink-0 items-center gap-2 px-4 hairline-b">
        <span className="text-[13px] font-medium">Incidents</span>
        <span className="num text-[11px] text-[var(--color-fg-3)]">{shown.length}</span>
        <span className="ml-auto text-[11px] text-[var(--color-fg-3)]">ranked by risk</span>
      </div>
      <div className="scroll min-h-0 flex-1">
        {shown.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-1 px-6 text-center">
            <span className="display text-[22px] text-[var(--color-fg-2)]">All quiet</span>
            <span className="text-[11px] text-[var(--color-fg-4)]">Routine activity is absorbed; nothing needs a human.</span>
          </div>
        )}
        {shown.map((i) => {
          const color = scoreColor(i.score, cfg)
          const active = selected === i.incident_id
          const muted = i.status === 'ack'
          return (
            <button key={i.incident_id} onClick={() => onSelect(i.incident_id)}
              className={`relative flex w-full items-start gap-3 px-4 py-3 text-left transition hairline-b ${active ? 'bg-[var(--color-surface-2)]' : 'hover:bg-[var(--color-surface-2)]/60'} ${muted ? 'opacity-60' : ''}`}>
              <span className="absolute inset-y-0 left-0 w-[2px]" style={{ background: color }} />
              <span className="num w-9 shrink-0 text-[22px] font-medium leading-none" style={{ color }}>{i.score}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] text-[var(--color-fg)]">{i.title.split(' — ')[0]}</span>
                <span className="mt-0.5 block truncate text-[11.5px] text-[var(--color-fg-2)]">{config?.areas[i.area]?.name ?? i.area}</span>
                <span className="mt-1.5 flex items-center gap-2 text-[11px] text-[var(--color-fg-3)]">
                  <span className="num">{localTime(i.first_signal_at)}</span>
                  <span>·</span>
                  <span style={{ color }}>{i.status === 'watch' ? 'Watch' : severityLabel(i.score, cfg)}</span>
                  {i.status !== 'open' && i.status !== 'watch' && <span className="capitalize">· {i.status === 'ack' ? 'acknowledged' : i.status}</span>}
                  <span className="ml-auto flex items-center gap-1">
                    {i.sources.map((s) => <span key={s} title={s} className="h-1.5 w-1.5 rounded-full" style={{ background: `var(--color-${s})` }} />)}
                  </span>
                </span>
              </span>
            </button>
          )
        })}
      </div>
    </section>
  )
}
