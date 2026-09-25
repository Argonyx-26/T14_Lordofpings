import { ChevronUp } from 'lucide-react'
import { eventLabel, fmt, localTime } from '../lib'
import type { ArgusEvent, SiteConfigView } from '../types'
import { SourceIcon } from './Symbols'

/**
 * The raw firehose ARGUS absorbs, or what each stream would page on its own (the "siloed" baseline it replaces).
 * Collapsed to a one-line ticker by default: it proves the system is alive without asking anyone to read it.
 */
export function StreamPanel({ events, total, config, siloed, onSiloed, open, onOpen }: {
  events: ArgusEvent[]; total: number; config: SiteConfigView | null; siloed: boolean; onSiloed: (v: boolean) => void
  open: boolean; onOpen: (v: boolean) => void
}) {
  const threshold = config?.thresholds.siloed_alert_severity ?? 0.25
  const latest = events[events.length - 1]

  return (
    <section className={`surface flex shrink-0 flex-col overflow-hidden ${open ? 'h-[240px]' : ''}`}>
      <div className="flex h-10 shrink-0 items-center gap-3 px-3.5">
        <button onClick={() => onOpen(!open)} aria-expanded={open} className="flex min-w-0 flex-1 items-center gap-3 text-left">
          <ChevronUp size={14} className={`shrink-0 text-[var(--color-fg-3)] transition ${open ? '' : 'rotate-180'}`} />
          <span className="shrink-0 text-[12.5px] font-medium">Raw signals</span>
          <span className="num shrink-0 text-[11px] text-[var(--color-fg-3)]">{fmt(total)}</span>
          {!open && latest && (
            <span key={latest.event_id} className="fade-in flex min-w-0 items-center gap-2 text-[11.5px] text-[var(--color-fg-3)]">
              <span className="text-[var(--color-fg-4)]">latest</span>
              <span className="num">{localTime(latest.t)}</span>
              <SourceIcon source={latest.source} size={11} />
              <span className="truncate text-[var(--color-fg-2)]">{eventLabel(latest.type)}</span>
              <span className="hidden truncate md:inline">· {config?.areas[latest.area]?.name ?? latest.area}</span>
            </span>
          )}
          {open && (
            <span className="truncate text-[11px] text-[var(--color-fg-3)]">
              {siloed ? 'what each stream would page a person with on its own' : 'every event from every stream; ARGUS absorbs these'}
            </span>
          )}
        </button>
        {open && (
          <div className="seg shrink-0">
            <button data-on={!siloed} onClick={() => onSiloed(false)}>All signals</button>
            <button data-on={siloed} onClick={() => onSiloed(true)} title="The baseline ARGUS replaces: each system alerting on its own">Siloed alerts</button>
          </div>
        )}
      </div>
      {open && <Rows events={events} config={config} siloed={siloed} threshold={threshold} />}
    </section>
  )
}

function Rows({ events, config, siloed, threshold }: { events: ArgusEvent[]; config: SiteConfigView | null; siloed: boolean; threshold: number }) {
  const rows = (siloed ? events.filter((e) => e.severity >= threshold) : events).slice(-80).reverse()
  return (
    <div className="scroll min-h-0 flex-1 py-1 hairline-t">
      {rows.map((e) => (
        <div key={e.event_id} className="grid grid-cols-[62px_14px_58px_1fr_minmax(0,150px)] items-center gap-2 px-3.5 py-[3px] text-[11.5px] hover:bg-[var(--color-surface-2)]">
          <span className="num text-[var(--color-fg-4)]">{localTime(e.t)}</span>
          <SourceIcon source={e.source} size={11} />
          <span className="num truncate text-[var(--color-fg-3)]">{e.sensor_id}</span>
          <span className={`truncate ${e.severity >= threshold ? 'text-[var(--color-fg)]' : 'text-[var(--color-fg-2)]'}`}>{eventLabel(e.type)}</span>
          <span className="truncate text-right text-[var(--color-fg-4)]">{config?.areas[e.area]?.name ?? e.area}</span>
        </div>
      ))}
      {rows.length === 0 && <div className="p-6 text-center text-[11px] text-[var(--color-fg-4)]">Press play to start the replay</div>}
    </div>
  )
}
