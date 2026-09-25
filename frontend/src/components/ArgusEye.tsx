import { useEffect, useId, useRef } from 'react'
import { LEVEL_COLOR, type Level } from '../lib'
import type { ArgusEvent, Clock } from '../types'

/**
 * The ARGUS eye: the whole system's state as one living instrument (Argus Panoptes, the hundred-eyed watcher).
 *
 *   outer ticks      the watch, turning while the replay plays
 *   camera ring      one segment per camera: lit with footage, coloured when its area has an incident
 *   stream rings     cameras, doors, phones: each pulses with its live signal rate
 *   particles        every real signal flows inward; routine ones fade halfway (absorbed), signals reach the pupil
 *   iris and pupil   dilate and change colour with the most urgent state on screen; the sweep turns at replay speed
 *
 * One requestAnimationFrame loop writes SVG attributes directly (no React render per frame); it stops when the tab
 * is hidden and everything is static under prefers-reduced-motion.
 */

export interface EyeCamera { id: string; footage: boolean; level: Level | null }

interface Props {
  size: number
  level: Level
  score: number | null
  events: ArgusEvent[]
  clock: Clock | null
  cameras: EyeCamera[]
  detail?: 'compact' | 'full'
  open?: number          // 0..1 eyelid, for the boot sequence
  contextMax?: number    // below this severity a signal is routine context
}

const SOURCES = ['cctv', 'door', 'device'] as const
const RING_R = { cctv: 72, door: 64, device: 56 } as const
const POOL = 40
const PUPIL: Record<Level, number> = { clear: 11, low: 12, watch: 15, high: 19, critical: 23 }

interface Particle { a: number; src: string; routine: boolean; born: number; dur: number; el: SVGCircleElement }

const reducedMotion = () => typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches

export function ArgusEye({ size, level, score, events, clock, cameras, detail = 'full', open = 1, contextMax = 0.2 }: Props) {
  const uid = useId().replace(/:/g, '')
  const ticks = useRef<SVGGElement>(null)
  const sweep = useRef<SVGGElement>(null)
  const rings = useRef<Record<string, SVGCircleElement | null>>({})
  const pupil = useRef<SVGCircleElement>(null)
  const flash = useRef<SVGCircleElement>(null)
  const pool = useRef<SVGGElement>(null)
  const live = useRef<Particle[]>([])
  const seen = useRef<string | null>(null)
  const rate = useRef<Record<string, number>>({ cctv: 0, door: 0, device: 0 })
  const st = useRef({ level, playing: !!clock?.playing, speed: clock?.speed ?? 1 })
  useEffect(() => { st.current = { level, playing: !!clock?.playing, speed: clock?.speed ?? 1 } })
  const color = LEVEL_COLOR[level]

  // New events become particles (the newest few per batch) and feed each stream's rate.
  useEffect(() => {
    if (!events.length) return
    const last = seen.current
    let start = last ? events.findIndex((e) => e.event_id === last) + 1 : Math.max(0, events.length - 6)
    if (start <= 0 && last) start = Math.max(0, events.length - 6)   // buffer rolled or replay rebuilt
    const fresh = events.slice(start).slice(-12)
    seen.current = events[events.length - 1].event_id
    if (reducedMotion() || !pool.current) return
    const now = performance.now()
    for (const e of fresh) {
      const src = SOURCES.includes(e.source as typeof SOURCES[number]) ? e.source : 'cctv'
      rate.current[src] = Math.min(1, rate.current[src] + (e.severity >= contextMax ? 0.35 : 0.08))
      const used = new Set(live.current.map((p) => p.el))
      const free = [...pool.current.children].find((c) => !used.has(c as SVGCircleElement)) as SVGCircleElement | undefined
      if (!free) continue
      live.current.push({
        a: Math.random() * Math.PI * 2, src, routine: e.severity < contextMax, born: now + Math.random() * 280,
        dur: e.severity < contextMax ? 900 : 1400, el: free,
      })
    }
  }, [events, contextMax])

  useEffect(() => {
    const still = reducedMotion()
    let raf = 0
    let last = performance.now()
    let tickA = 0, sweepA = 0
    const ringA: Record<string, number> = { cctv: 0, door: 120, device: 240 }
    let pr = PUPIL[st.current.level]
    let flashT = 0
    const frame = (now: number) => {
      raf = requestAnimationFrame(frame)
      const dt = Math.min(0.05, (now - last) / 1000)
      last = now
      const { playing, speed, level } = st.current
      const tempo = playing ? Math.min(3, 0.6 + speed / 10) : 0.15
      tickA += dt * 4 * tempo
      sweepA += dt * 70 * tempo
      ticks.current?.setAttribute('transform', `rotate(${tickA} 100 100)`)
      sweep.current?.setAttribute('transform', `rotate(${sweepA} 100 100)`)
      SOURCES.forEach((s, k) => {
        ringA[s] += dt * (k % 2 ? -1 : 1) * (8 + 18 * rate.current[s]) * tempo
        rate.current[s] = Math.max(0, rate.current[s] - dt * 0.35)
        const r = rings.current[s]
        if (r) {
          r.setAttribute('transform', `rotate(${ringA[s]} 100 100)`)
          r.setAttribute('stroke-opacity', String(0.28 + 0.62 * rate.current[s]))
          r.setAttribute('stroke-width', String(1.2 + 2.2 * rate.current[s]))
        }
      })
      pr += (PUPIL[level] - pr) * Math.min(1, dt * 4)                 // critically damped toward the level's size
      pupil.current?.setAttribute('r', pr.toFixed(2))
      // particles
      const keep: Particle[] = []
      for (const p of live.current) {
        const t = (now - p.born) / p.dur
        if (t < 0) { p.el.setAttribute('opacity', '0'); keep.push(p); continue }
        if (t >= 1) {
          p.el.setAttribute('opacity', '0')
          if (!p.routine) flashT = now
          continue
        }
        const e = 1 - Math.pow(1 - t, 3)
        const r0 = 90
        const r1 = p.routine ? 50 : pr + 2
        const r = r0 - (r0 - r1) * e
        const a = p.a + e * 0.6
        p.el.setAttribute('cx', (100 + r * Math.cos(a)).toFixed(2))
        p.el.setAttribute('cy', (100 + r * Math.sin(a)).toFixed(2))
        p.el.setAttribute('r', p.routine ? '1.1' : '1.8')
        p.el.setAttribute('fill', `var(--color-${p.src})`)
        p.el.setAttribute('opacity', (p.routine ? (1 - t) * 0.7 : t < 0.85 ? 1 : (1 - t) / 0.15).toFixed(2))
        keep.push(p)
      }
      live.current = keep
      const f = flash.current
      if (f) {
        const k = Math.max(0, 1 - (now - flashT) / 700)
        f.setAttribute('r', (pr + 3 + (1 - k) * 14).toFixed(2))
        f.setAttribute('stroke-opacity', (k * 0.8).toFixed(2))
      }
      if (still) cancelAnimationFrame(raf)
    }
    raf = requestAnimationFrame(frame)
    return () => cancelAnimationFrame(raf)
  }, [])

  const full = detail === 'full'
  const segs = cameras.length || 6
  const arc = (i: number, r: number, gap: number) => {
    const a0 = ((i / segs) * 360 + gap / 2 - 90) * (Math.PI / 180)
    const a1 = (((i + 1) / segs) * 360 - gap / 2 - 90) * (Math.PI / 180)
    return `M${100 + r * Math.cos(a0)} ${100 + r * Math.sin(a0)} A${r} ${r} 0 0 1 ${100 + r * Math.cos(a1)} ${100 + r * Math.sin(a1)}`
  }

  return (
    <svg width={size} height={size} viewBox="0 0 200 200" role="img" className="block shrink-0 overflow-visible"
      aria-label={`ARGUS: ${level === 'clear' ? 'all clear' : `${level}${score !== null ? `, risk ${score}` : ''}`}`}>
      <defs>
        <radialGradient id={`iris-${uid}`} cx="50%" cy="50%" r="50%">
          <stop offset="0%" style={{ stopColor: color, stopOpacity: 0.95 }} />
          <stop offset="55%" style={{ stopColor: color, stopOpacity: 0.35 }} />
          <stop offset="100%" style={{ stopColor: color, stopOpacity: 0.05 }} />
        </radialGradient>
        <linearGradient id={`sweep-${uid}`} x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" style={{ stopColor: color, stopOpacity: 0 }} />
          <stop offset="1" style={{ stopColor: color, stopOpacity: 0.32 }} />
        </linearGradient>
        <mask id={`lid-${uid}`}>
          <ellipse cx="100" cy="100" rx="104" ry={Math.max(0.01, 104 * open)} fill="white" />
        </mask>
      </defs>

      <g mask={open < 1 ? `url(#lid-${uid})` : undefined}>
        {/* the watch: 60 ticks, every fifth long */}
        <g ref={ticks}>
          {Array.from({ length: 60 }, (_, i) => {
            const a = (i / 60) * Math.PI * 2
            const long = i % 5 === 0
            const r0 = long ? 91 : 93.5
            return <line key={i} x1={100 + r0 * Math.cos(a)} y1={100 + r0 * Math.sin(a)} x2={100 + 97 * Math.cos(a)} y2={100 + 97 * Math.sin(a)}
              stroke="var(--color-fg-3)" strokeOpacity={long ? 0.7 : 0.3} strokeWidth={long ? 1.2 : 0.8} />
          })}
        </g>

        {/* cameras */}
        {Array.from({ length: segs }, (_, i) => {
          const c = cameras[i]
          const stroke = c?.level ? LEVEL_COLOR[c.level] : c?.footage ? 'var(--color-fg-2)' : 'var(--color-fg-4)'
          return <path key={i} d={arc(i, 84, 7)} fill="none" stroke={stroke} strokeWidth={c?.level ? 3.2 : 2} strokeLinecap="round"
            strokeOpacity={c?.level ? 1 : c?.footage ? 0.65 : 0.4} className={c?.level ? 'breathe' : undefined}>
            {c && <title>{`${c.id}${c.level ? ` · ${c.level}` : c.footage ? ' · footage' : ' · no footage now'}`}</title>}
          </path>
        })}

        {/* streams */}
        {SOURCES.map((s) => (
          <circle key={s} ref={(el) => { rings.current[s] = el }} cx="100" cy="100" r={RING_R[s]} fill="none"
            stroke={`var(--color-${s})`} strokeOpacity="0.3" strokeWidth="1.2" strokeLinecap="round"
            strokeDasharray={s === 'cctv' ? '2 5 14 5' : s === 'door' ? '1 6' : '6 3 1 3'} />
        ))}

        {/* sweep */}
        <g ref={sweep}>
          <path d="M100 100 L148 100 A48 48 0 0 0 139 72 Z" fill={`url(#sweep-${uid})`} />
        </g>

        {/* iris and pupil */}
        <circle cx="100" cy="100" r="44" fill={`url(#iris-${uid})`} style={{ transition: 'fill .6s' }} />
        <circle cx="100" cy="100" r="44" fill="none" stroke={color} strokeOpacity="0.45" strokeWidth="0.8" />
        <circle ref={flash} cx="100" cy="100" r="20" fill="none" stroke={color} strokeWidth="1.5" strokeOpacity="0" />
        <circle ref={pupil} cx="100" cy="100" r={PUPIL[level]} fill="#040506" stroke={color} strokeOpacity="0.9" strokeWidth="1" />
        <circle cx="92" cy="92" r="3.2" fill="#fff" fillOpacity="0.75" />
        {full && score !== null && level !== 'clear' && (
          <text x="100" y="105.5" textAnchor="middle" fontSize="15" fontWeight="600" fill="var(--color-fg)" fontFamily="var(--font-sans)">{score}</text>
        )}

        {/* particle pool */}
        <g ref={pool}>
          {Array.from({ length: POOL }, (_, i) => <circle key={i} r="1.5" opacity="0" />)}
        </g>
      </g>
    </svg>
  )
}
