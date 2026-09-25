import { ChevronRight } from 'lucide-react'
import { useEffect, useState } from 'react'
import { API, MOCK, SOURCE_LABEL, fmt } from '../lib'
import type { Summary } from '../types'

interface Metrics { available: boolean; ground_truth_alerted?: number; ground_truth_total?: number }

/** The product in one line: everything the streams emit, what siloed thresholds would page, what ARGUS surfaces. */
export function MetricsStrip({ summary }: { summary: Summary | null }) {
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  useEffect(() => {
    if (MOCK) return
    fetch(API + '/api/metrics').then((r) => r.json()).then(setMetrics).catch(() => setMetrics(null))
  }, [])

  const raw = summary?.raw_events ?? 0
  const surfaced = (summary?.incidents_open ?? 0) + (summary?.incidents_watch ?? 0)
  const reduction = raw ? (1 - surfaced / raw) * 100 : 0

  return (
    <section className="flex shrink-0 items-stretch px-5 py-3 hairline-b">
      <Stage label="Events ingested" value={fmt(raw)} note="every signal, every stream" />
      <Arrow />
      <Stage label="Per-stream alerts" value={fmt(summary?.siloed_alerts)} note="what siloed thresholds would page" />
      <Arrow />
      <Stage label="Incidents surfaced" value={fmt(surfaced)} note={`${summary?.incidents_open ?? 0} open · ${summary?.incidents_watch ?? 0} on watch`} strong />
      <div className="mx-6 w-px bg-[var(--color-hair)]" />
      <Stage label="Noise removed" value={raw ? `${reduction.toFixed(1)}%` : '—'} note="of events never reach a human" />
      {metrics?.available && (
        <>
          <div className="mx-6 w-px bg-[var(--color-hair)]" />
          <Stage label="Staged incidents caught" value={`${metrics.ground_truth_alerted}/${metrics.ground_truth_total}`} note="vs MEVA ground truth" />
        </>
      )}
      <div className="ml-auto flex flex-col justify-center gap-1.5">
        {Object.entries(summary?.by_source ?? {}).map(([src, n]) => (
          <div key={src} className="flex items-center gap-2 text-[11px]">
            <span className="h-1.5 w-1.5 rounded-full" style={{ background: `var(--color-${src})` }} />
            <span className="w-28 text-[var(--color-fg-3)]">{SOURCE_LABEL[src] ?? src}</span>
            <span className="num w-12 text-right text-[var(--color-fg-2)]">{fmt(n)}</span>
          </div>
        ))}
      </div>
    </section>
  )
}

function Stage({ label, value, note, strong }: { label: string; value: string; note: string; strong?: boolean }) {
  return (
    <div className="flex min-w-32 flex-col">
      <span className="eyebrow">{label}</span>
      <span className={`display mt-1.5 text-[40px] ${strong ? 'text-[var(--color-fg)]' : 'text-[var(--color-fg-2)]'}`}>{value}</span>
      <span className="mt-1 text-[11px] text-[var(--color-fg-4)]">{note}</span>
    </div>
  )
}

function Arrow() {
  return <ChevronRight className="mx-3 self-center text-[var(--color-fg-4)]" size={18} strokeWidth={1.25} />
}
