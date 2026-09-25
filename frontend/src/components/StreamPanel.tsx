import { localTime } from '../lib'
import type { ArgusEvent, SiteConfigView } from '../types'

/** The firehose, or what each stream would page on its own (the "siloed" baseline ARGUS replaces). */
export function StreamPanel({ events, config, siloed, onSiloed }: {
  events: ArgusEvent[]; config: SiteConfigView | null; siloed: boolean; onSiloed: (v: boolean) => void
}) {
  const threshold = config?.thresholds.siloed_alert_severity ?? 0.25
  const rows = (siloed ? events.filter((e) => e.severity >= threshold) : events).slice(-80).reverse()
  return (
    <section className="surface flex min-h-0 flex-1 flex-col">
      <div className="flex h-10 shrink-0 items-center gap-3 px-4 hairline-b">
        <span className="text-[13px] font-medium">Event stream</span>
        <span className="text-[11px] text-[var(--color-fg-3)]">
          {siloed ? 'what each stream would page on its own' : 'every event from every stream'}
        </span>
        <div className="seg ml-auto">
          <button data-on={!siloed} onClick={() => onSiloed(false)}>All events</button>
          <button data-on={siloed} onClick={() => onSiloed(true)}>Siloed alerts</button>
        </div>
      </div>
      <div className="scroll min-h-0 flex-1 py-1">
        {rows.map((e) => (
          <div key={e.event_id} className="grid grid-cols-[64px_10px_96px_1fr_140px] items-center gap-2 px-4 py-[3px] text-[11.5px] hover:bg-[var(--color-surface-2)]">
            <span className="num text-[var(--color-fg-4)]">{localTime(e.t)}</span>
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: `var(--color-${e.source})` }} />
            <span className="num truncate text-[var(--color-fg-3)]">{e.sensor_id}</span>
            <span className={`truncate ${e.severity >= threshold ? 'text-[var(--color-fg)]' : 'text-[var(--color-fg-2)]'}`}>{e.type.replaceAll('_', ' ')}</span>
            <span className="truncate text-right text-[var(--color-fg-4)]">{config?.areas[e.area]?.name ?? e.area}</span>
          </div>
        ))}
        {rows.length === 0 && <div className="p-6 text-center text-[11px] text-[var(--color-fg-4)]">Press play to start the replay</div>}
      </div>
    </section>
  )
}
