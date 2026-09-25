import { scoreColor } from '../lib'
import type { Incident, SiteConfigView } from '../types'

// Schematic of the MEVA facility, north up (positions follow the MEVA site map, not to scale).
const LAYOUT: Record<string, { x: number; y: number; w: number; h: number }> = {
  school: { x: 150, y: 10, w: 110, h: 70 },
  plaza: { x: 60, y: 10, w: 85, h: 70 },
  parking: { x: 110, y: 90, w: 120, h: 50 },
  bus_station: { x: 20, y: 100, w: 80, h: 60 },
}

export function SiteMap({ config, incidents }: { config: SiteConfigView | null; incidents: Incident[] }) {
  const live = incidents.filter((i) => ['open', 'escalated', 'ack', 'watch'].includes(i.status))
  const top = (area: string) => Math.max(0, ...live.filter((i) => i.area === area).map((i) => i.score))
  return (
    <section className="panel p-3">
      <div className="label mb-2">Site · {config?.site_name}</div>
      <svg viewBox="0 0 280 170" className="w-full">
        <text x="270" y="12" fontSize="9" textAnchor="end" fill="var(--color-dim)">N ↑</text>
        {Object.entries(LAYOUT).map(([area, r]) => {
          const s = top(area)
          const color = s ? scoreColor(s, config ?? undefined) : 'var(--color-line)'
          return (
            <g key={area}>
              <rect x={r.x} y={r.y} width={r.w} height={r.h} rx="6" fill={s ? `color-mix(in srgb, ${color} 22%, transparent)` : 'var(--color-panel-2)'}
                stroke={color} strokeWidth={s ? 2 : 1} className={s ? 'pulse' : ''} />
              <text x={r.x + 6} y={r.y + 14} fontSize="9" fill="var(--color-ink)">{config?.areas[area]?.name ?? area}</text>
              {s > 0 && <text x={r.x + r.w - 6} y={r.y + r.h - 6} fontSize="12" textAnchor="end" fontWeight="700" fill={color}>{s}</text>}
            </g>
          )
        })}
      </svg>
    </section>
  )
}
