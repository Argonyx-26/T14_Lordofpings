import type { SiteConfigView } from './types'

// Served by the backend (demo): same origin. Vite dev server on :5173: talk to the backend on :8000.
// (`location` is absent outside a browser, e.g. in unit tests.)
const loc = typeof location === 'undefined' ? undefined : location
export const API = import.meta.env.VITE_ARGUS_API ?? (!loc || loc.port === '5173' ? 'http://localhost:8000' : loc.origin)
export const WS_URL = API.replace(/^http/, 'ws') + '/ws'
// ?mock, or a build made for the hosted offline demo (VITE_ARGUS_MOCK=1, GitHub Pages): no backend, a real snapshot
export const MOCK = import.meta.env.VITE_ARGUS_MOCK === '1' || (!!loc && new URLSearchParams(loc.search).has('mock'))

const UTC_OFFSET_H = -4 // MEVA site local time (EDT)

/** "2018-03-15.14-50-01.14-55-01.school.G420" -> {start, end} UTC epoch seconds */
export function clipWindow(stem: string): { start: number; end: number; camera: string } {
  const [date, s, e, , camera] = stem.split('.')
  const toEpoch = (hms: string) => {
    const [h, m, sec] = hms.split('-').map(Number)
    const [y, mo, d] = date.split('-').map(Number)
    return Date.UTC(y, mo - 1, d, h - UTC_OFFSET_H, m, sec) / 1000
  }
  return { start: toEpoch(s), end: toEpoch(e), camera }
}

export function clipAt(cfg: SiteConfigView, camera: string, t: number): string | null {
  for (const stem of cfg.clips) {
    const w = clipWindow(stem)
    if (w.camera === camera && t >= w.start && t < w.end) return stem
  }
  return null
}

export function localTime(t: number): string {
  const d = new Date((t + UTC_OFFSET_H * 3600) * 1000)
  return d.toISOString().slice(11, 19)
}

export async function post(path: string, body: unknown) {
  const r = await fetch(API + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) throw new Error(`${path}: ${r.status}`)
  return r.json()
}

export const SOURCE_LABEL: Record<string, string> = {
  cctv: 'Camera analytics',
  door: 'Door sensors',
  device: 'Phone locations',
  auth: 'Access logs',
}

export const PROVENANCE_LABEL: Record<string, string> = {
  computed: 'computed by Argus',
  annotation_derived: 'from dataset annotations',
  recorded: 'recorded GPS',
}

export function scoreColor(score: number, cfg?: SiteConfigView): string {
  const open = cfg?.thresholds.open_threshold ?? 55
  const watch = cfg?.thresholds.watch_threshold ?? 35
  if (score >= open + 20) return 'var(--color-crit)'
  if (score >= open) return 'var(--color-high)'
  if (score >= watch) return 'var(--color-watch)'
  return 'var(--color-fg-4)'
}

export function severityLabel(score: number, cfg?: SiteConfigView): string {
  const open = cfg?.thresholds.open_threshold ?? 55
  const watch = cfg?.thresholds.watch_threshold ?? 35
  if (score >= open + 20) return 'Critical'
  if (score >= open) return 'High'
  if (score >= watch) return 'Watch'
  return 'Low'
}

export const fmt = (n: number | undefined) => (n ?? 0).toLocaleString('en-US')

// ---- plain language ------------------------------------------------------------------------------------------

/** What each signal means to a person, not the rule's internal name. */
export const EVENT_LABEL: Record<string, string> = {
  abandoned_object: 'Bag left unattended',
  abandoned_package: 'Package left unattended',
  custody_change: 'Bag taken by someone else',
  running: 'Person running',
  loitering: 'Person lingering',
  vehicle_in_ped_zone: 'Vehicle in pedestrian area',
  occupancy: 'Head count',
  occupancy_anomaly: 'Unusual number of people',
  door_activity: 'Door opened',
  door_open: 'Door opened',
  door_surge: 'Unusual door traffic',
  device_enter: 'Phone arrived',
  device_exit: 'Phone left',
  device_fast_exit: 'Phone left quickly',
  device_crowding: 'Phones gathering',
  device_exodus: 'Many phones leaving',
  device_dispersal: 'Area emptied suddenly',
  weapon_visible: 'Weapon seen on a person',
  violence: 'Fight or violent struggle',
  person_down: 'Person on the ground',
  hand_off: 'Hand-to-hand exchange',
  dealing_pattern: 'Repeated hand-offs (possible dealing)',
  camera_obstructed: 'Camera view lost',
  camera_restored: 'Camera view restored',
}

export const eventLabel = (type: string) => EVENT_LABEL[type] ?? type.replaceAll('_', ' ').replace(/^./, (c) => c.toUpperCase())

// ---- severity ------------------------------------------------------------------------------------------------

export type Level = 'critical' | 'high' | 'watch' | 'low' | 'clear'

/** One severity scale for everything on screen (same bands as scoreColor / severityLabel). */
export function levelOf(score: number, cfg?: SiteConfigView): Level {
  const l = severityLabel(score, cfg)
  return l === 'Critical' ? 'critical' : l === 'High' ? 'high' : l === 'Watch' ? 'watch' : 'low'
}

export const LEVEL_COLOR: Record<Level, string> = {
  critical: 'var(--color-crit)', high: 'var(--color-high)', watch: 'var(--color-watch)', low: 'var(--color-off)', clear: 'var(--color-ok)',
}

/** Statuses that still sit in front of a human. */
export const ACTIVE = ['open', 'escalated', 'ack'] as const
export const isActive = (status: string) => (ACTIVE as readonly string[]).includes(status)
const RANK: Record<string, number> = { open: 0, escalated: 0, ack: 1, watch: 2 }

/** Incidents a person should see, most urgent first: undecided before handled before on-watch, then by risk. */
export function rankIncidents<T extends { status: string; score: number }>(list: T[]): T[] {
  return list.filter((i) => i.status in RANK).sort((a, b) => RANK[a.status] - RANK[b.status] || b.score - a.score)
}

export const STATUS_LABEL: Record<string, string> = {
  candidate: 'Signal', watch: 'On watch', open: 'Awaiting decision', ack: 'Acknowledged', escalated: 'Escalated', dismissed: 'Dismissed',
}

/** 75 -> "1:15", 3725 -> "1:02:05" */
export function duration(s: number): string {
  s = Math.max(0, Math.floor(s))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`
}

/** The cameras on the wall, in display order. */
export const WALL = ['G421', 'G419', 'G420', 'G638', 'G336', 'G331']

// ---- cameras -------------------------------------------------------------------------------------------------

/** Start of the next recording from `camera` after `t`, or null. */
export function nextClipStart(cfg: SiteConfigView, camera: string, t: number): number | null {
  let best: number | null = null
  for (const stem of cfg.clips) {
    const w = clipWindow(stem)
    if (w.camera === camera && w.start > t && (best === null || w.start < best)) best = w.start
  }
  return best
}

/** Cameras that saw an incident: those with camera evidence (strongest first), then the rest of its area. */
export function camerasFor(
  inc: { area: string } | null, evidence: { source: string; sensor_id: string; severity: number }[], cfg: SiteConfigView, wall: string[],
): string[] {
  if (!inc) return []
  const seen = evidence.filter((e) => e.source === 'cctv' && wall.includes(e.sensor_id))
    .sort((a, b) => b.severity - a.severity).map((e) => e.sensor_id)
  const inArea = wall.filter((c) => cfg.cameras[c]?.area === inc.area)
  return [...new Set([...seen, ...inArea])]
}

/**
 * The camera on the main screen. A camera the operator pinned wins; otherwise the one that saw the incident in
 * front of them (as a VMS alarm pops the nearest camera), preferring one that has footage right now.
 */
export function pickPrimary(
  wall: string[], pinned: string | null, incidentCams: string[], hasFootage: (c: string) => boolean,
): { camera: string; why: 'pinned' | 'incident' | 'auto' } {
  if (pinned && wall.includes(pinned)) return { camera: pinned, why: 'pinned' }
  const withFootage = incidentCams.find(hasFootage)
  if (withFootage) return { camera: withFootage, why: 'incident' }
  if (incidentCams.length) return { camera: incidentCams[0], why: 'incident' }
  return { camera: wall.find(hasFootage) ?? wall[0], why: 'auto' }
}

/** "gemini-flash-latest" -> "Gemini", "claude-…" -> "Claude" */
export const modelName = (model?: string | null) =>
  model?.startsWith('gemini') ? 'Gemini' : model?.startsWith('claude') ? 'Claude' : model ?? 'the model'

/** The single most urgent state on screen (Astro rule: roll many statuses up into the highest) and the incident behind it. */
export function situation<T extends { status: string; score: number }>(incidents: T[], cfg?: SiteConfigView): { level: Level; top: T | null } {
  const ranked = rankIncidents(incidents)
  const active = ranked.filter((i) => isActive(i.status))
  if (active.length) return { level: levelOf(Math.max(...active.map((i) => i.score)), cfg), top: active[0] }
  const watching = ranked.filter((i) => i.status === 'watch')
  return watching.length ? { level: 'watch', top: watching[0] } : { level: 'clear', top: null }
}

/** Show the boot sequence: once per session, not for deep links (?plan, ?upload, ?noboot), never under reduced motion. */
export function shouldBoot(): boolean {
  if (typeof window === 'undefined') return false
  const q = new URLSearchParams(location.search)
  if (q.has('noboot') || q.has('plan') || q.has('upload')) return false
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return false
  try { return !sessionStorage.getItem('argus-booted') } catch { return true }
}
