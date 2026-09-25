import { localTime } from '../lib'
import type { ArgusEvent, SiteConfigView } from '../types'

/** Siloed view: what each stream would page on its own, next to the raw firehose. */
export function StreamPanel({ events, config, siloed }: { events: ArgusEvent[]; config: SiteConfigView | null; siloed: boolean }) {
  const threshold = config?.thresholds.siloed_alert_severity ?? 0.25
  const rows = (siloed ? events.filter((e) => e.severity >= threshold) : events).slice(-60).reverse()
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      {rows.map((e) => (
        <div key={e.event_id} className="flex items-center gap-2 border-b border-[var(--color-line)]/50 px-3 py-1 text-[11px]">
          <span className="num w-14 text-[var(--color-dim)]">{localTime(e.t)}</span>
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: `var(--color-${e.source})` }} />
          <span className="w-24 truncate text-[var(--color-mute)]">{e.sensor_id}</span>
          <span className="flex-1 truncate">{e.type.replaceAll('_', ' ')}</span>
          <span className="w-20 truncate text-right text-[var(--color-dim)]">{config?.areas[e.area]?.name ?? e.area}</span>
        </div>
      ))}
      {rows.length === 0 && <div className="p-4 text-center text-xs text-[var(--color-dim)]">No events yet — press Play</div>}
    </div>
  )
}
