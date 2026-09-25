import { useEffect, useState } from 'react'
import { API, MOCK, SOURCE_LABEL } from '../lib'
import type { Summary } from '../types'

interface Metrics {
  available: boolean
  ground_truth_alerted?: number
  ground_truth_total?: number
}

export function MetricsStrip({ summary }: { summary: Summary | null }) {
  const [metrics, setMetrics] = useState<Metrics | null>(null)
  useEffect(() => {
    if (MOCK) return
    fetch(API + '/api/metrics').then((r) => r.json()).then(setMetrics).catch(() => setMetrics(null))
  }, [])

  const surfaced = (summary?.incidents_open ?? 0) + (summary?.incidents_watch ?? 0)
  return (
    <section className="panel flex items-stretch divide-x divide-[var(--color-line)]">
      <Stat label="Raw events" value={summary?.raw_events} note="every signal from every stream" />
      <Stat label="Siloed alerts" value={summary?.siloed_alerts} note="what per-stream thresholds would page" />
      <Stat label="ARGUS incidents" value={surfaced} accent note={`${summary?.incidents_open ?? 0} open · ${summary?.incidents_watch ?? 0} watch`} />
      <div className="flex flex-1 items-center gap-4 px-4">
        {Object.entries(summary?.by_source ?? {}).map(([src, n]) => (
          <div key={src} className="flex items-center gap-2 text-xs">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: `var(--color-${src})` }} />
            <span className="text-[var(--color-mute)]">{SOURCE_LABEL[src] ?? src}</span>
            <span className="num">{n}</span>
          </div>
        ))}
      </div>
      {metrics?.available && (
        <Stat label="Staged incidents caught" value={`${metrics.ground_truth_alerted}/${metrics.ground_truth_total}`}
          note="vs MEVA ground truth (offline eval)" />
      )}
    </section>
  )
}

function Stat({ label, value, note, accent }: { label: string; value?: number | string; note: string; accent?: boolean }) {
  return (
    <div className="px-4 py-2.5">
      <div className="label">{label}</div>
      <div className={`num text-2xl font-semibold ${accent ? 'text-[var(--color-accent)]' : ''}`}>{value ?? '–'}</div>
      <div className="text-[11px] text-[var(--color-dim)]">{note}</div>
    </div>
  )
}
