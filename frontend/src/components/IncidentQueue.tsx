import { localTime, scoreColor } from '../lib'
import type { Incident, SiteConfigView } from '../types'

const ORDER: Record<string, number> = { open: 0, escalated: 0, ack: 1, watch: 2 }

export function IncidentQueue({ incidents, config, selected, onSelect }: {
  incidents: Incident[]; config: SiteConfigView | null; selected: string | null; onSelect: (id: string) => void
}) {
  const shown = incidents
    .filter((i) => i.status in ORDER)
    .sort((a, b) => ORDER[a.status] - ORDER[b.status] || b.score - a.score)

  return (
    <section className="panel flex min-h-0 min-w-0 flex-col">
      <div className="flex items-center justify-between border-b border-[var(--color-line)] px-3 py-2">
        <span className="label">Incident queue · ranked by risk</span>
        <span className="num text-xs text-[var(--color-mute)]">{shown.length}</span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {shown.length === 0 && (
          <div className="p-6 text-center text-sm text-[var(--color-dim)]">Quiet. Routine activity is being absorbed.</div>
        )}
        {shown.map((i) => (
          <button key={i.incident_id} onClick={() => onSelect(i.incident_id)}
            className={`flex w-full items-start gap-3 border-b border-[var(--color-line)] px-3 py-2.5 text-left hover:bg-[var(--color-panel-2)] ${selected === i.incident_id ? 'bg-[var(--color-panel-2)]' : ''}`}>
            <div className="num flex h-10 w-10 shrink-0 items-center justify-center rounded-md text-base font-bold text-black"
              style={{ background: scoreColor(i.score, config ?? undefined) }}>{i.score}</div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium">{i.title}</div>
              <div className="mt-0.5 flex items-center gap-2 text-[11px] text-[var(--color-mute)]">
                <span className="num">{localTime(i.first_signal_at)}</span>
                <span className="uppercase">{i.status}</span>
                {i.sources.map((s) => (
                  <span key={s} className="rounded px-1.5" style={{ background: `color-mix(in srgb, var(--color-${s}) 25%, transparent)` }}>{s}</span>
                ))}
                {i.common_cause && <span className="text-[var(--color-watch)]">common cause</span>}
              </div>
            </div>
          </button>
        ))}
      </div>
    </section>
  )
}
