import { duration, scoreColor } from '../lib'
import type { Incident, Intel, SiteConfigView } from '../types'

const W = 320
const H = 240
const PAD = 18
const SHORT: Record<string, string> = { school: 'School', plaza: 'Plaza', parking: 'Parking', bus_station: 'Bus station' }

/** Site plan drawn from the real fusion-area polygons (areas.geojson) and camera positions, north up, to scale. */
export function SiteMap({ config, incidents, primary, onFocus, intel, selected }: {
  config: SiteConfigView | null; incidents: Incident[]; primary: string | null; onFocus: (camera: string) => void
  intel?: Intel | null; selected?: string | null
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
  // intel overlays: where no camera can see, where to look next (near-repeat watch), and incidents linked into a pattern
  const centre: Record<string, [number, number]> = Object.fromEntries(Object.entries(geometry).map(([area, ring]) => {
    const p = ring.map(([lon, lat]) => proj(lon, lat))
    return [area, [p.reduce((a, q) => a + q[0], 0) / p.length, p.reduce((a, q) => a + q[1], 0) / p.length]]
  }))
  const blind = new Set(intel?.coverage.areas.filter((a) => !a.streams.cctv).map((a) => a.area) ?? [])
  const watchNext = new Set(intel?.watch?.areas.filter((a) => a.heightened).map((a) => a.area) ?? [])
  const arcs = (intel?.links ?? []).filter((l) => l.from_area !== l.to_area && centre[l.from_area] && centre[l.to_area])
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
          <pattern id="blind" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <path d="M0 0V5" stroke="var(--color-fg-4)" strokeWidth="0.8" opacity="0.55" />
          </pattern>
          <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M0 0L8 4L0 8Z" fill="context-stroke" />
          </marker>
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
              {blind.has(area) && <path d={d} fill="url(#blind)" pointerEvents="none"><title>No camera sees this area: phone counts only</title></path>}
              {watchNext.has(area) && (
                <path d={d} fill="none" stroke="var(--color-accent)" strokeWidth="1.1" strokeDasharray="4 3" className="watch-next" pointerEvents="none" />
              )}
              {blind.has(area) && (
                <text x={cx} y={cy + (score > 0 ? 24 : 9)} textAnchor="middle" fontSize="5.5" fill="var(--color-fg-3)" fontFamily="var(--font-sans)">no camera</text>
              )}
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
        {/* incidents linked into a pattern (argus/patterns.py): an arc from the earlier area to the later one */}
        {arcs.map((l) => {
          const [x1, y1] = centre[l.from_area]
          const [x2, y2] = centre[l.to_area]
          const mine = !!selected && (l.from === selected || l.to === selected)
          const mx = (x1 + x2) / 2 - (y2 - y1) * 0.25
          const my = (y1 + y2) / 2 + (x2 - x1) * 0.25
          const stroke = l.kind === 'concurrent' ? 'var(--color-watch)' : mine ? 'var(--color-accent)' : 'var(--color-fg-2)'
          return (
            <g key={l.from + l.to} pointerEvents="none">
              <title>{`${l.from} → ${l.to}: ${l.why}`}</title>
              <path d={`M${x1} ${y1 + 6}Q${mx} ${my} ${x2} ${y2 + 6}`} fill="none" stroke={stroke} strokeWidth={mine ? 1.6 : 1.1}
                strokeDasharray={l.kind === 'concurrent' ? '3 2' : undefined} markerEnd="url(#arrow)" className="link-flow" />
              <text x={mx} y={my} textAnchor="middle" fontSize="6" fill={stroke} fontFamily="var(--font-mono)">
                {l.gap_s > 0 ? `+${duration(l.gap_s)}` : 'same time'}
              </text>
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
      {intel && (
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10.5px] text-[var(--color-fg-3)]">
          {intel.coverage.visibility !== null && (
            <span title={`Visibility: ${intel.coverage.visibility_basis}`}>
              visibility <span className="num text-[var(--color-fg-2)]">{intel.coverage.visibility}%</span>
            </span>
          )}
          {blind.size > 0 && <span className="flex items-center gap-1"><svg width="10" height="8"><rect width="10" height="8" fill="url(#blind)" stroke="var(--color-fg-4)" strokeWidth="0.5" /></svg> no camera</span>}
          {watchNext.size > 0 && intel.watch && (
            <span className="flex items-center gap-1" title={intel.watch.basis}>
              <svg width="12" height="8"><path d="M0 4H12" stroke="var(--color-accent)" strokeDasharray="3 2" /></svg>
              watch next · <span className="num">{duration(intel.watch.remaining_s)}</span> left
            </span>
          )}
          {arcs.length > 0 && <span className="flex items-center gap-1"><svg width="12" height="8"><path d="M0 4H12" stroke="var(--color-fg-2)" /></svg> linked incidents</span>}
        </div>
      )}
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
