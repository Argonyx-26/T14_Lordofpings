import { ChevronRight, CircleCheck, CircleX, ShieldCheck } from 'lucide-react'
import { m } from 'motion/react'
import { useEffect, useRef, useState } from 'react'
import { API, LEVEL_COLOR, MOCK, duration, isActive, levelOf, rankIncidents, type Level } from '../lib'
import type { ArgusEvent, Clock, Incident, SiteConfigView, Summary } from '../types'
import { ArgusEye, type EyeCamera } from './ArgusEye'
import { Decode, Roll } from './Motion'
import { StatusSymbol } from './Symbols'

interface GroundTruth { kind: string; camera: string; area: string; time: string; result: string; latency_s: number | null; peak_score: number }
interface Metrics {
  available: boolean
  ground_truth_alerted?: number
  ground_truth_total?: number
  ground_truth?: GroundTruth[]
  false_incidents?: unknown[]
}

interface Props {
  summary: Summary | null
  incidents: Incident[]
  config: SiteConfigView | null
  clock: Clock | null
  onSelect: (id: string) => void
  events: ArgusEvent[]
  cameras: EyeCamera[]
  eye: boolean            // false while the boot sequence still holds the eye
}

/**
 * The first three seconds: what is happening and how serious it is (left), what ARGUS is doing about the noise
 * (middle), and whether to trust it (right). Every number here is live or measured, none are decorative.
 */
export function SituationBand({ summary, incidents, config, clock, onSelect, events, cameras, eye }: Props) {
  const cfg = config ?? undefined
  const ranked = rankIncidents(incidents)
  const active = ranked.filter((i) => isActive(i.status))
  const watching = ranked.filter((i) => i.status === 'watch')
  const undecided = active.filter((i) => i.status === 'open')
  const top = active[0] ?? watching[0] ?? null

  // consolidate: the band takes the most urgent state on screen
  const level: Level = active.length ? levelOf(Math.max(...active.map((i) => i.score)), cfg) : watching.length ? 'watch' : 'clear'
  const color = LEVEL_COLOR[level]
  const headline = undecided.length ? `${undecided.length} incident${undecided.length > 1 ? 's' : ''} need${undecided.length > 1 ? '' : 's'} a decision`
    : active.length ? 'Being handled' : watching.length ? 'On watch' : 'All clear'
  const since = top && clock ? clock.sim_t - (top.opened_at ?? top.first_signal_at) : null

  const raw = summary?.raw_events ?? 0
  const surfaced = summary?.incidents_open ?? 0      // on-watch incidents are below the bar for a person
  const decided = incidents.filter((i) => ['ack', 'escalated', 'dismissed'].includes(i.status)).length

  return (
    <section className="grid shrink-0 grid-cols-1 gap-px hairline-b md:grid-cols-[minmax(0,1.35fr)_minmax(0,1.2fr)] xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1.15fr)_minmax(0,0.7fr)]"
      style={{ background: 'var(--color-hair)' }}>
      {/* 1 · the situation */}
      <button onClick={() => top && onSelect(top.incident_id)} disabled={!top}
        className="relative flex min-w-0 items-center gap-4 overflow-hidden px-5 py-3 text-left transition enabled:hover:brightness-110"
        style={{ background: `linear-gradient(90deg, color-mix(in srgb, ${color} ${level === 'clear' ? 6 : 13}%, var(--color-bg)), var(--color-bg) 70%)` }}>
        <span className="absolute inset-y-0 left-0 w-[3px]" style={{ background: color }} />
        <div className="-my-1 shrink-0" style={{ width: 76, height: 76 }}>
          {eye && (
            <m.div layoutId="argus-eye" style={{ width: 76, height: 76 }} transition={{ type: 'spring', stiffness: 120, damping: 20 }}>
              <ArgusEye size={76} level={level} score={top?.score ?? null} events={events} clock={clock} cameras={cameras} detail="compact"
                contextMax={config?.thresholds.context_max_severity} />
            </m.div>
          )}
        </div>
        <div key={`${level}:${top?.incident_id}`} className="arrive min-w-0 flex-1">
          <div className="flex items-center gap-2">
            {level === 'clear' ? <CircleCheck size={13} strokeWidth={2} style={{ color }} /> : <StatusSymbol level={level} size={11} pulse={undecided.length > 0} />}
            <span className="eyebrow" style={{ color }}>{headline}</span>
            {active.length + watching.length > 1 && (
              <span className="text-[11px] text-[var(--color-fg-3)]">· {active.length} active{watching.length ? `, ${watching.length} on watch` : ''}</span>
            )}
          </div>
          <div className="mt-1 truncate text-[19px] font-semibold tracking-[-0.01em] text-[var(--color-fg)]">
            <Decode text={top ? top.title.split(' — ')[0] : 'Nothing needs a person right now'} />
          </div>
          <div className="mt-0.5 truncate text-[12px] text-[var(--color-fg-2)]">
            {top ? (
              <>
                {config?.areas[top.area]?.name ?? top.area}
                <span className="text-[var(--color-fg-4)]"> · </span>risk <span className="num text-[var(--color-fg)]">{top.score}</span>
                {since !== null && <><span className="text-[var(--color-fg-4)]"> · </span>{top.opened_at ? 'open for' : 'building for'} <span className="num">{duration(since)}</span></>}
              </>
            ) : `Watching ${Object.keys(config?.cameras ?? {}).length} cameras, the doors and phone locations across ${Object.keys(config?.areas ?? {}).length} areas`}
          </div>
        </div>
        {top && <ChevronRight size={16} className="shrink-0 text-[var(--color-fg-3)]" />}
      </button>

      {/* 2 · what ARGUS is doing: the funnel from every signal to a human decision */}
      <div className="flex min-w-0 flex-col justify-center px-5 py-3" style={{ background: 'var(--color-bg)' }}>
        <div className="flex items-center gap-2">
          <span className="eyebrow">From signals to decisions</span>
          {raw > 0 && (
            <span className="ml-auto text-[11px] text-[var(--color-fg-3)]">
              <span className="num text-[var(--color-fg)]">{(raw ? (1 - surfaced / raw) * 100 : 0).toFixed(1)}%</span> never reach a person
            </span>
          )}
        </div>
        <div className="mt-2 grid grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr] items-end gap-1.5">
          <Stage value={raw} label="signals" hint="Every event from every stream so far" />
          <Arrow />
          <Stage value={summary?.siloed_alerts ?? 0} label="stream alerts" hint="What separate camera, door and GPS systems would each have paged" />
          <Arrow />
          <Stage value={surfaced} label="incidents" hint={`Signals ARGUS fused by place and time and scored high enough for a person${summary?.incidents_watch ? ` (plus ${summary.incidents_watch} on watch, below that bar)` : ''}`} strong />
          <Arrow />
          <Stage value={decided} label="decided" hint="Incidents a person has acknowledged, escalated or dismissed" strong />
        </div>
      </div>

      {/* 3 · should I trust it */}
      <Validation />
    </section>
  )
}

function Stage({ value, label, hint, strong }: { value: number; label: string; hint: string; strong?: boolean }) {
  return (
    <div className="min-w-0" title={hint}>
      <Roll value={value} className={`figure block text-[22px] ${strong ? 'text-[var(--color-fg)]' : 'text-[var(--color-fg-2)]'}`} />
      <div className="mt-1 truncate text-[11px] text-[var(--color-fg-3)]">{label}</div>
    </div>
  )
}

function Arrow() {
  return <ChevronRight size={14} strokeWidth={1.5} className="mb-[18px] text-[var(--color-fg-4)]" />
}

/** Measured against MEVA's human-annotated staged incidents (which ARGUS never reads). Click for the list. */
function Validation() {
  const [m, setM] = useState<Metrics | null>(null)
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (MOCK) return
    fetch(API + '/api/metrics').then((r) => r.json()).then(setM).catch(() => setM(null))
  }, [])
  useEffect(() => {
    const close = (e: MouseEvent) => { if (root.current && !root.current.contains(e.target as Node)) setOpen(false) }
    window.addEventListener('mousedown', close)
    return () => window.removeEventListener('mousedown', close)
  }, [])
  if (!m?.available) return <div className="hidden xl:block" style={{ background: 'var(--color-bg)' }} />
  const falseN = m.false_incidents?.length ?? 0

  return (
    <div ref={root} className="relative hidden min-w-0 xl:block" style={{ background: 'var(--color-bg)' }}>
      <button onClick={() => setOpen(!open)} aria-expanded={open}
        className="flex h-full w-full flex-col justify-center px-5 py-3 text-left transition hover:bg-[var(--color-surface)]">
        <span className="eyebrow flex items-center gap-1.5"><ShieldCheck size={12} strokeWidth={1.75} /> Tested on ground truth</span>
        <span className="mt-2 flex items-baseline gap-1.5">
          <span className="figure text-[22px] text-[var(--color-fg)]">{m.ground_truth_alerted}/{m.ground_truth_total}</span>
          <span className="text-[11px] text-[var(--color-fg-3)]">staged incidents caught</span>
        </span>
        <span className="mt-1 text-[11px] text-[var(--color-fg-3)]">
          <span className="num text-[var(--color-fg-2)]">{falseN}</span> false incident{falseN === 1 ? '' : 's'} · details
        </span>
      </button>
      {open && m.ground_truth && (
        <div className="pop absolute right-2 top-full z-40 mt-1 w-[340px] rounded-xl p-3.5"
          style={{ background: 'var(--color-surface-2)', boxShadow: '0 18px 50px rgb(0 0 0 / .6), inset 0 0 0 1px var(--color-hair-2)' }}>
          <p className="mb-2.5 text-[11.5px] leading-relaxed text-[var(--color-fg-3)]">
            Actors staged these in the MEVA recordings among ordinary passers-by. The labels are used only to score
            ARGUS afterwards; the detectors never see them.
          </p>
          <ul className="space-y-1.5">
            {m.ground_truth.map((g) => (
              <li key={g.time + g.camera} className="flex items-center gap-2 text-[12px]">
                {g.result === 'alerted'
                  ? <CircleCheck size={13} strokeWidth={2} className="shrink-0 text-[var(--color-ok)]" />
                  : <CircleX size={13} strokeWidth={2} className="shrink-0 text-[var(--color-fg-4)]" />}
                <span className="num text-[var(--color-fg-3)]">{g.time.slice(11, 19)}</span>
                <span className="capitalize text-[var(--color-fg)]">{g.kind.replaceAll('_', ' ')}</span>
                <span className="num text-[var(--color-fg-4)]">{g.camera}</span>
                <span className="ml-auto text-[11px] text-[var(--color-fg-3)]">
                  {g.result === 'alerted' ? (g.latency_s === null ? 'caught'
                    : g.latency_s < 0 ? `flagged ${Math.round(-g.latency_s)} s before` : `caught in ${Math.round(g.latency_s)} s`) : 'missed'}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
