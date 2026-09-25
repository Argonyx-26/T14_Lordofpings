import type { SiteConfigView } from './types'

// Served by the backend (demo): same origin. Vite dev server on :5173: talk to the backend on :8000.
export const API = import.meta.env.VITE_ARGUS_API ?? (location.port === '5173' ? 'http://localhost:8000' : location.origin)
export const WS_URL = API.replace(/^http/, 'ws') + '/ws'
export const MOCK = new URLSearchParams(location.search).has('mock')

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
  cctv: 'CCTV analytics',
  door: 'Door sensor',
  device: 'Device location',
  auth: 'Auth logs',
}

export const PROVENANCE_LABEL: Record<string, string> = {
  computed: 'computed',
  annotation_derived: 'from annotations',
  recorded: 'recorded',
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
