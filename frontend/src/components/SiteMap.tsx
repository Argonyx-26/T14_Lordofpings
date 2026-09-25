import { scoreColor } from '../lib'
import type { Incident, SiteConfigView } from '../types'

const W = 320
const H = 240
const PAD = 18
const SHORT: Record<string, string> = { school: 'School', plaza: 'Plaza', parking: 'Parking', bus_station: 'Bus station' }

/** Site plan drawn from the real fusion-area polygons (areas.geojson) and camera positions, north up, to scale. */
export function SiteMap({ config, incidents, primary, onFocus }: {
  config: SiteConfigView | null; incidents: Incident[]; primary: string | null; onFocus: (camera: string) => void
}) {
  const geometry = config?.geometry ?? {}
  const cams = Object.entries(config?.cameras ?? {}).filter(([id, c]) => c.pos && id !== 'G474')
  const pts: [number, number][] = [...Object.values(geometry).flat(), ...cams.map(([, c]) => [c.pos![1], c.pos![0]] as [number, number])]
  if (!pts.length) return null

  // Equirectangular projection around the site centre (metres), fitted to the box.
  const lat0 = pts.reduce((s, p) => s + p[1], 0) / pts.length
  const mx = 111320 * Math.cos((lat0 * Math.PI) / 180)
  const my = 110574
  const xs = pts.map((p) => p[0] * mx)
  const ys = pts.map((p) => p[1] * my)
  const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
  const s = Math.min((W - 2 * PAD) / (maxX - minX), (H - 2 * PAD) / (maxY - minY))
  const ox = (W - (maxX - minX) * s) / 2
  const oy = (H - (maxY - minY) * s) / 2
  const proj = (lon: number, lat: number) => [ox + (lon * mx - minX) * s, H - (oy + (lat * my - minY) * s)] as const
  const scaleM = 50

  const live = incidents.filter((i) => ['open', 'escalated', 'ack', 'watch'].includes(i.status))
  const top = (area: string) => Math.max(0, ...live.filter((i) => i.area === area).map((i) => i.score))

  return (
    <section className="surface shrink-0 px-3.5 pb-2.5 pt-3">
      <div className="mb-1 flex items-center">
        <span className="text-[13px] font-medium">Site</span>
        <span className="ml-auto truncate text-[11px] text-[var(--color-fg-3)]">
          {primary && config?.cameras[primary] ? <>on screen: <span className="num text-[var(--color-accent)]">{primary}</span>, looking at {SHORT[config.cameras[primary].area] ?? config.cameras[primary].area}</> : 'click a camera to view it'}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="max-h-[240px] w-full">
        <defs>
          <pattern id="grid" width="16" height="16" patternUnits="userSpaceOnUse">
            <path d="M16 0H0V16" fill="none" stroke="var(--color-hair)" strokeWidth="0.5" />
          </pattern>
        </defs>
        <rect width={W} height={H} fill="url(#grid)" />
        {Object.entries(geometry).map(([area, ring]) => {
          const score = top(area)
          const color = score ? scoreColor(score, config ?? undefined) : null
          const d = ring.map(([lon, lat], i) => `${i ? 'L' : 'M'}${proj(lon, lat).join(' ')}`).join('') + 'Z'
          const cx = ring.reduce((a, p) => a + proj(p[0], p[1])[0], 0) / ring.length
          const cy = ring.reduce((a, p) => a + proj(p[0], p[1])[1], 0) / ring.length
          return (
            <g key={area}>
              <path d={d} fill={color ? `color-mix(in srgb, ${color} 16%, transparent)` : 'var(--color-surface-2)'}
                stroke={color ?? 'var(--color-hair-2)'} strokeWidth={color ? 1.25 : 0.75} />
              <text x={cx} y={cy} textAnchor="middle" fontSize="6.5" letterSpacing="0.9" fill={color ?? 'var(--color-fg-3)'}
                fontFamily="var(--font-sans)" fontWeight="500">
                {(SHORT[area] ?? area).toUpperCase()}
              </text>
              {score > 0 && (
                <text x={cx} y={cy + 13} textAnchor="middle" fontSize="12" fill={color!} fontFamily="var(--font-mono)">{score}</text>
              )}
            </g>
          )
        })}
        {/* what the camera on the main screen is looking at: a sight cone to the area it watches, outlined */}
        {(() => {
          const cam = primary ? config?.cameras[primary] : null
          const ring = cam?.area ? geometry[cam.area] : null
          if (!cam?.pos || !ring) return null
          const [x, y] = proj(cam.pos[1], cam.pos[0])
          const pts = ring.map(([lon, lat]) => proj(lon, lat))
          const cx = pts.reduce((a, p) => a + p[0], 0) / pts.length
          const cy = pts.reduce((a, p) => a + p[1], 0) / pts.length
          const ang = Math.atan2(cy - y, cx - x)
          const len = Math.max(18, Math.min(70, Math.hypot(cx - x, cy - y) * 1.15))
          const half = 0.42                                     // ~48 degree cone: a typical CCTV lens
          const p1 = [x + len * Math.cos(ang - half), y + len * Math.sin(ang - half)]
          const p2 = [x + len * Math.cos(ang + half), y + len * Math.sin(ang + half)]
          const d = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0]} ${p[1]}`).join('') + 'Z'
          return (
            <g pointerEvents="none">
              <path d={d} fill="none" stroke="var(--color-accent)" strokeWidth="1.2" strokeDasharray="3 2" />
              <path d={`M${x} ${y}L${p1[0]} ${p1[1]}A${len} ${len} 0 0 1 ${p2[0]} ${p2[1]}Z`}
                fill="color-mix(in srgb, var(--color-accent) 22%, transparent)" stroke="var(--color-accent)" strokeWidth="0.6" />
            </g>
          )
        })()}
        {groupCameras(cams.map(([id, c]) => ({ id, area: c.area, xy: proj(c.pos![1], c.pos![0]) }))).map((g) => {
          const [x, y] = g.xy
          const hot = g.areas.some((a) => top(a) >= (config?.thresholds.open_threshold ?? 55))
          const onScreen = !!primary && g.ids.includes(primary)
          const target = onScreen ? primary! : g.ids[0]
          return (
            <g key={g.ids.join()} role="button" tabIndex={0} className="cursor-pointer outline-none"
              aria-label={`Show ${g.ids.join(' or ')} in the main view`}
              onClick={() => onFocus(target)} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onFocus(target)}>
              <title>{g.ids.map((id) => `${id} · ${config?.cameras[id].label}`).join('\n')}</title>
              <circle cx={x} cy={y} r="9" fill="transparent" />
              {hot && <circle cx={x} cy={y} r="4" fill="none" stroke="var(--color-high)" className="ring" />}
              {onScreen && <circle cx={x} cy={y} r="4.2" fill="none" stroke="var(--color-accent)" strokeWidth="1.2" />}
              <circle cx={x} cy={y} r="1.9" fill={hot ? 'var(--color-high)' : onScreen ? 'var(--color-accent)' : 'var(--color-fg-2)'} />
              <text x={x + 5} y={y - 3} fontSize="5.5" fill={onScreen ? 'var(--color-accent)' : 'var(--color-fg-3)'} fontFamily="var(--font-mono)">{g.ids.join(' · ')}</text>
            </g>
          )
        })}
        {/* north arrow + scale bar */}
        <g transform={`translate(${W - 14} 14)`} fill="var(--color-fg-3)">
          <path d="M0 -8 L3.5 4 L0 1.5 L-3.5 4 Z" />
          <text y="13" textAnchor="middle" fontSize="7" fontFamily="var(--font-mono)">N</text>
        </g>
        <g transform={`translate(10 ${H - 10})`} stroke="var(--color-fg-3)" strokeWidth="0.75">
          <path d={`M0 -3V0H${scaleM * s}V-3`} fill="none" />
          <text x={scaleM * s + 4} y="0" fontSize="7" fill="var(--color-fg-3)" stroke="none" fontFamily="var(--font-mono)">{scaleM} m</text>
        </g>
      </svg>
    </section>
  )
}

/** Merge cameras mounted within a few pixels of each other so their labels don't collide. */
function groupCameras(cams: { id: string; area: string; xy: readonly [number, number] }[]) {
  const groups: { ids: string[]; areas: string[]; xy: readonly [number, number] }[] = []
  for (const c of cams) {
    const g = groups.find((g) => Math.hypot(g.xy[0] - c.xy[0], g.xy[1] - c.xy[1]) < 6)
    if (g) { g.ids.push(c.id); g.areas.push(c.area) } else groups.push({ ids: [c.id], areas: [c.area], xy: c.xy })
  }
  return groups
}
