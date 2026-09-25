import { EyeOff, Footprints, ScanEye, Waypoints } from 'lucide-react'
import { LEVEL_COLOR, duration, levelOf, localTime } from '../lib'
import type { AreaCoverage, Incident, Intel, PatternLink, Series, SiteConfigView } from '../types'

const KIND: Record<PatternLink['kind'], string> = {
  near_repeat: 'walkable',
  repeat: 'same place',
  concurrent: 'too soon to walk',
}
const SHORT: Record<string, string> = { school: 'School', plaza: 'Plaza', parking: 'Parking', bus_station: 'Bus station', live: 'Stage' }
const areaShort = (a: string) => SHORT[a] ?? a

/**
 * The layer above incidents, for one incident: the series it belongs to (same behaviour, a walkable gap apart) drawn
 * as a chain in time, each link with its reason; or, when it stands alone, the near-repeat watch it started.
 */
export function PatternCard({ incident, intel, incidents, config, onSelect }: {
  incident: Incident; intel: Intel | null; incidents: Record<string, Incident>; config: SiteConfigView | null; onSelect: (id: string) => void
}) {
  if (!intel) return null
  const series = intel.series.find((s) => s.incidents.includes(incident.incident_id))
  const watch = intel.watch && intel.watch.after === incident.incident_id ? intel.watch : null
  if (!series && !watch) return null
  const mine = intel.links.filter((l) => l.from === incident.incident_id || l.to === incident.incident_id)

  return (
    <div className="rounded-lg" style={{ boxShadow: 'inset 0 0 0 1px var(--color-hair-2)' }}>
      <div className="px-3 pb-3 pt-2.5">
        <div className="eyebrow flex items-center gap-1.5">
          <Waypoints size={11} strokeWidth={2} /> {series ? 'Part of a pattern' : 'Near-repeat watch'}
          <span className="font-normal normal-case tracking-normal text-[var(--color-fg-4)]">· across incidents, by behaviour, place and time</span>
        </div>
        {series && (
          <>
            <p className="mt-2 text-[13px] font-medium leading-snug text-[var(--color-fg)]">{series.title}</p>
            <SeriesChain series={series} links={intel.links} incidents={incidents} config={config} current={incident.incident_id} onSelect={onSelect} />
            <ul className="mt-2 space-y-1.5">
              {mine.map((l) => {
                const other = l.from === incident.incident_id ? l.to : l.from
                return (
                  <li key={l.from + l.to}>
                    <button onClick={() => onSelect(other)} className="group flex w-full items-start gap-2 rounded-md px-1.5 py-1 text-left transition hover:bg-[var(--color-surface-2)]">
                      <Footprints size={12} strokeWidth={1.75} className="mt-0.5 shrink-0" style={{ color: l.kind === 'concurrent' ? 'var(--color-watch)' : 'var(--color-fg-3)' }} />
                      <span className="min-w-0 flex-1 text-[12px] leading-relaxed text-[var(--color-fg-2)]">
                        <span className="num text-[var(--color-fg)]">{other}</span>{' '}
                        <span className="chip ml-0.5 align-[1px]">{KIND[l.kind]}</span>
                        <span className="block">{l.why}</span>
                      </span>
                    </button>
                  </li>
                )
              })}
            </ul>
            <p className="mt-2 text-[11px] leading-relaxed text-[var(--color-fg-4)]">{series.reading}</p>
          </>
        )}
        {!series && watch && <WatchSummary intel={intel} config={config} />}
      </div>
      {series && watch && <div className="px-3 pb-3 pt-2.5 hairline-t"><WatchSummary intel={intel} config={config} /></div>}
    </div>
  )
}

/** Where to look next after this incident, while the near-repeat window is open. */
function WatchSummary({ intel, config }: { intel: Intel; config: SiteConfigView | null }) {
  const w = intel.watch!
  const hot = w.areas.filter((a) => a.heightened)
  const blind = w.areas.filter((a) => a.blind)
  return (
    <div className="text-[12px] leading-relaxed text-[var(--color-fg-2)]">
      <p className="flex items-center gap-1.5 text-[12.5px] text-[var(--color-fg)]">
        <ScanEye size={13} strokeWidth={1.75} className="text-[var(--color-accent)]" />
        Watch next: {hot.map((a, k) => (
          <span key={a.area}>{k > 0 && ' and '}<span className="text-[var(--color-accent)]">{config?.areas[a.area]?.name ?? a.area}</span>
            {a.cameras.length > 0 && <span className="num text-[var(--color-fg-3)]"> ({a.cameras.join(', ')})</span>}</span>
        ))}
      </p>
      <p className="mt-1 text-[11.5px] text-[var(--color-fg-3)]">
        Until <span className="num text-[var(--color-fg-2)]">{localTime(w.until)}</span> · the whole site is <span className="num">{duration(w.site_walk_s)}</span> on foot
        {blind.length > 0 && <> · <EyeOff size={11} className="inline align-[-1px]" /> no camera sees {blind.map((a) => config?.areas[a.area]?.name ?? a.area).join(', ')}</>}
      </p>
      <p className="mt-1 text-[11px] text-[var(--color-fg-4)]">{w.basis}</p>
    </div>
  )
}

/** The series in time, left to right: one node per incident (its level, area and time), each link labelled. */
function SeriesChain({ series, links, incidents, config, current, onSelect }: {
  series: Series; links: PatternLink[]; incidents: Record<string, Incident>; config: SiteConfigView | null; current: string; onSelect: (id: string) => void
}) {
  const W = 320
  const H = 86
  const Y = 46
  const n = series.incidents.length
  const x = (k: number) => (n === 1 ? W / 2 : 22 + (k * (W - 44)) / (n - 1))
  const idx = Object.fromEntries(series.incidents.map((id, k) => [id, k]))
  const own = links.filter((l) => l.from in idx && l.to in idx)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 w-full" role="img" aria-label={`Pattern: ${series.title}`}>
      {own.map((l) => {
        const a = x(idx[l.from])
        const b = x(idx[l.to])
        const far = Math.abs(idx[l.to] - idx[l.from]) > 1
        const lift = far ? 40 : 16
        const mid = (a + b) / 2
        const conc = l.kind === 'concurrent'
        return (
          <g key={l.from + l.to}>
            <path d={`M${a} ${Y} Q${mid} ${Y - lift} ${b} ${Y}`} fill="none" stroke={conc ? 'var(--color-watch)' : 'var(--color-fg-3)'}
              strokeWidth="1" strokeDasharray={conc ? '3 2' : undefined} />
            {(
              <text x={mid} y={Y - lift / 2 - 3} textAnchor="middle" fontSize="7" fill="var(--color-fg-3)" fontFamily="var(--font-mono)">
                {l.gap_s > 0 ? `+${duration(l.gap_s)}` : 'same time'}{!far && l.distance_m ? ` · ${l.distance_m} m` : ''}
              </text>
            )}
          </g>
        )
      })}
      {series.incidents.map((id, k) => {
        const inc = incidents[id]
        const color = inc ? LEVEL_COLOR[inc.status === 'watch' ? 'watch' : levelOf(inc.score, config ?? undefined)] : 'var(--color-fg-3)'
        const me = id === current
        return (
          <g key={id} role="button" tabIndex={0} className="cursor-pointer outline-none" onClick={() => onSelect(id)}
            onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onSelect(id)} aria-label={`Open ${id}`}>
            <title>{inc?.title ?? id}</title>
            {me && <circle cx={x(k)} cy={Y} r="8" fill="none" stroke="var(--color-accent)" strokeWidth="1.2" />}
            <circle cx={x(k)} cy={Y} r="4.5" fill={color} />
            <text x={x(k)} y={Y + 20} textAnchor="middle" fontSize="7.5" fill={me ? 'var(--color-fg)' : 'var(--color-fg-2)'} fontFamily="var(--font-sans)">
              {areaShort(inc?.area ?? '')}
            </text>
            <text x={x(k)} y={Y + 31} textAnchor="middle" fontSize="7" fill="var(--color-fg-3)" fontFamily="var(--font-mono)">
              {inc ? localTime(inc.first_signal_at).slice(0, 5) : ''} · {id.replace('INC-', '')}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

/**
 * What the sensors in this incident's area could ever say, next to what they said: a single-source incident in a
 * one-stream area is all the evidence that area can give, not weak evidence.
 */
export function CoverageNote({ incident, area }: { incident: Incident; area: AreaCoverage | undefined }) {
  if (!area) return null
  const LABEL: Record<string, string> = { cctv: 'cameras', door: 'door sensors', device: 'phone counts' }
  const present = (Object.keys(area.streams) as (keyof typeof area.streams)[]).filter((s) => area.streams[s])
  const agree = present.filter((s) => incident.sources.includes(s)).length
  const silent = present.filter((s) => !incident.sources.includes(s))
  return (
    <div className="mt-3 rounded-md px-2.5 py-2 text-[11.5px] leading-relaxed text-[var(--color-fg-2)]" style={{ background: 'var(--color-surface-2)' }}>
      <span className="text-[var(--color-fg)]">What could agree here:</span>{' '}
      {present.length ? <>
        {area.name} is covered by {present.map((s) => LABEL[s]).join(', ')}; <span className="num text-[var(--color-fg)]">{agree} of {present.length}</span> agree
        {silent.length > 0 && <> ({silent.map((s) => LABEL[s]).join(', ')} {silent.length > 1 ? 'are' : 'is'} quiet)</>}.
        {area.ceiling.corroboration !== null && <> The most corroboration this area can give is <span className="num">×{area.ceiling.corroboration}</span>.</>}
      </> : <>no stream covers {area.name}.</>}
      {area.offline.length > 0 && <span className="block text-[var(--color-watch)]">Not recording now: <span className="num">{area.offline.join(', ')}</span></span>}
      {area.blind.length > 0 && <span className="block text-[var(--color-fg-3)]"><EyeOff size={11} className="inline align-[-1px]" /> Blind here to {area.blind.join(', ').toLowerCase()}</span>}
    </div>
  )
}
