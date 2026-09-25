import { Cctv, DoorOpen, KeyRound, Smartphone } from 'lucide-react'
import { LEVEL_COLOR, SOURCE_LABEL, type Level } from '../lib'

/**
 * Status symbol: colour plus a shape, so severity reads without colour vision (Astro UXDS status system).
 * critical = diamond, high = triangle, watch = square, low = hollow circle, clear = filled circle.
 */
export function StatusSymbol({ level, size = 10, pulse = false }: { level: Level; size?: number; pulse?: boolean }) {
  const c = LEVEL_COLOR[level]
  return (
    <svg width={size} height={size} viewBox="0 0 10 10" aria-hidden className={`shrink-0 ${pulse ? 'breathe' : ''}`}>
      {level === 'critical' && <path d="M5 0.3 9.7 5 5 9.7 0.3 5Z" fill={c} />}
      {level === 'high' && <path d="M5 0.8 9.6 9.2H0.4Z" fill={c} />}
      {level === 'watch' && <rect x="1.2" y="1.2" width="7.6" height="7.6" rx="1.2" fill={c} />}
      {level === 'low' && <circle cx="5" cy="5" r="3.6" fill="none" stroke={c} strokeWidth="1.5" />}
      {level === 'clear' && <circle cx="5" cy="5" r="4" fill={c} />}
    </svg>
  )
}

const SOURCE_ICON = { cctv: Cctv, door: DoorOpen, device: Smartphone, auth: KeyRound } as const

/** A data source: its icon in its colour, labelled for screen readers and on hover. */
export function SourceIcon({ source, size = 12 }: { source: string; size?: number }) {
  const Icon = SOURCE_ICON[source as keyof typeof SOURCE_ICON] ?? Cctv
  return (
    <Icon size={size} strokeWidth={1.9} aria-label={SOURCE_LABEL[source] ?? source} className="shrink-0"
      style={{ color: `var(--color-${source})` }}>
      <title>{SOURCE_LABEL[source] ?? source}</title>
    </Icon>
  )
}
