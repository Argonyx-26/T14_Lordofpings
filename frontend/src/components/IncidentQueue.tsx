import { LEVEL_COLOR, STATUS_LABEL, duration, levelOf, rankIncidents, severityLabel } from '../lib'
import type { Clock, Incident, SiteConfigView } from '../types'
import { SourceIcon, StatusSymbol } from './Symbols'

interface Props {
  incidents: Incident[]
  config: SiteConfigView | null
  clock: Clock | null
  selected: string | null
  onSelect: (id: string) => void
}

/** Incidents a person should see: undecided first, then handled, then on watch; by risk within each. */
export function IncidentQueue({ incidents, config, clock, selected, onSelect }: Props) {
  const shown = rankIncidents(incidents)
  const cfg = config ?? undefined
  const undecided = shown.filter((i) => i.status === 'open').length

  return (
    <section className="surface fill-sm flex min-h-0 min-w-0 flex-1 flex-col">
      <div className="flex h-11 shrink-0 items-center gap-2 px-3.5 hairline-b">
        <span className="text-[13px] font-medium">Incidents</span>
        <span className="num text-[11px] text-[var(--color-fg-3)]">{shown.length}</span>
        <span className="ml-auto text-[11px] text-[var(--color-fg-3)]">
          {undecided ? <><span className="num" style={{ color: 'var(--color-fg)' }}>{undecided}</span> awaiting decision</> : 'ranked by risk'}
        </span>
      </div>
      <div className="scroll scroll-sm min-h-0 flex-1" role="listbox" aria-label="Incidents">
        {shown.length === 0 && (
          <div className="flex h-full min-h-[140px] flex-col items-center justify-center gap-1.5 px-6 text-center">
            <StatusSymbol level="clear" size={12} />
            <span className="text-[14px] font-medium text-[var(--color-fg-2)]">All quiet</span>
            <span className="text-[11.5px] leading-relaxed text-[var(--color-fg-4)]">Routine activity is absorbed. Incidents appear here the moment signals agree.</span>
          </div>
        )}
        {shown.map((i) => {
          const level = i.status === 'watch' ? 'watch' : levelOf(i.score, cfg)
          const color = LEVEL_COLOR[level]
          const active = selected === i.incident_id
          const handled = i.status === 'ack' || i.status === 'escalated'
          const since = clock ? clock.sim_t - (i.opened_at ?? i.first_signal_at) : 0
          return (
            <button key={i.incident_id} onClick={() => onSelect(i.incident_id)} role="option" aria-selected={active}
              className={`arrive relative flex w-full items-start gap-3 px-3.5 py-3 text-left transition hairline-b ${active ? 'bg-[var(--color-surface-3)]' : 'hover:bg-[var(--color-surface-2)]'}`}>
              <span className="absolute inset-y-0 left-0 w-[3px] transition-opacity" style={{ background: color, opacity: active ? 1 : i.status === 'open' ? 0.8 : 0.3 }} />
              <span className="flex w-9 shrink-0 flex-col items-start gap-1.5 pt-0.5">
                <span key={i.score} className="figure text-[20px]" style={{ color: handled ? 'var(--color-fg-2)' : 'var(--color-fg)' }}>{i.score}</span>
                <span className="flex items-center gap-1 text-[10px]" style={{ color }}>
                  <StatusSymbol level={level} size={7} />{i.status === 'watch' ? 'Watch' : severityLabel(i.score, cfg)}
                </span>
              </span>
              <span className="min-w-0 flex-1">
                <span className={`block text-[13px] leading-snug ${handled ? 'text-[var(--color-fg-2)]' : 'text-[var(--color-fg)]'}`}>{i.title.split(' — ')[0]}</span>
                <span className="mt-0.5 block truncate text-[11.5px] text-[var(--color-fg-3)]">
                  {config?.areas[i.area]?.name ?? i.area} · <span className="num">{duration(since)}</span> {i.opened_at ? 'open' : 'building'}
                </span>
                <span className="mt-1.5 flex items-center gap-2">
                  <span className={`text-[11px] ${i.status === 'open' ? 'text-[var(--color-fg)]' : 'text-[var(--color-fg-3)]'}`}>{STATUS_LABEL[i.status]}</span>
                  <span className="ml-auto flex items-center gap-1.5">
                    {i.sources.map((s) => <SourceIcon key={s} source={s} size={11} />)}
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
