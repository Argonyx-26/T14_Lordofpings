import { useState } from 'react'
import { MOCK, PROVENANCE_LABEL, SOURCE_LABEL, localTime, post, scoreColor } from '../lib'
import type { ArgusEvent, Incident, SiteConfigView } from '../types'
import type { Role } from './TopBar'

interface Props {
  incident: Incident | null
  config: SiteConfigView | null
  role: Role
  evidence: ArgusEvent[]
  onJump: (e: ArgusEvent) => void
  replayingLeadUp?: boolean
}

export function IncidentDetail({ incident, config, role, evidence, onJump, replayingLeadUp }: Props) {
  const [busy, setBusy] = useState(false)

  if (!incident) {
    return <section className="panel flex items-center justify-center p-6 text-sm text-[var(--color-dim)]">Select an incident</section>
  }

  const act = async (action: 'ack' | 'escalate' | 'dismiss') => {
    if (MOCK || replayingLeadUp) return
    setBusy(true)
    try { await post(`/api/incidents/${incident.incident_id}/action`, { action, role }) } finally { setBusy(false) }
  }
  const b = incident.score_breakdown
  const factors: [string, number, string][] = [
    ['Severity', b.severity, 'strongest signal per source, combined'],
    ['Confidence', b.confidence, 'mean detector confidence'],
    ['Criticality', b.criticality, 'importance of this area'],
    ['Corroboration', b.corroboration / 1.45, `×${b.corroboration} · ${incident.sources.length} independent source(s)`],
    ['Time of day', b.time_factor / 1.3, `×${b.time_factor}`],
    ['Feedback', b.feedback, `×${b.feedback} from operator dismissals`],
  ]
  const actionText = incident.brief ? config?.playbook[incident.brief.action_id] ?? incident.brief.action_id : null

  return (
    <section className="panel flex min-h-0 min-w-0 flex-col">
      <div className="flex items-start gap-3 border-b border-[var(--color-line)] p-3">
        <div className="num flex h-14 w-14 shrink-0 items-center justify-center rounded-lg text-2xl font-bold text-black"
          style={{ background: scoreColor(incident.score, config ?? undefined) }}>{incident.score}</div>
        <div className="min-w-0">
          <div className="text-base font-semibold">{incident.title}</div>
          <div className="mt-1 text-xs text-[var(--color-mute)]">
            {incident.incident_id} · {incident.status.toUpperCase()} · first signal {localTime(incident.first_signal_at)} · peak {incident.peak_score}
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3">
        {replayingLeadUp && (
          <div className="rounded-md border border-[var(--color-watch)] px-3 py-2 text-xs text-[var(--color-watch)]">
            Replaying the lead-up: press Play and this incident re-forms as its evidence arrives.
          </div>
        )}
        {incident.brief && (
          <div className="rounded-lg border border-[var(--color-line)] bg-[var(--color-panel-2)] p-3">
            <div className="label mb-1">Brief · {incident.brief.generated_by === 'llm' ? 'AI-written, checked against evidence' : 'template'}</div>
            <p className="text-sm">{incident.brief.summary}</p>
            <p className="mt-1 text-sm text-[var(--color-mute)]">{incident.brief.why}</p>
            {actionText && <p className="mt-2 text-sm"><span className="text-[var(--color-accent)]">Recommended:</span> {actionText}</p>}
          </div>
        )}

        <div>
          <div className="label mb-2">Why this score</div>
          {factors.map(([name, v, note]) => (
            <div key={name} className="mb-1.5 grid grid-cols-[92px_1fr_auto] items-center gap-2 text-xs">
              <span className="text-[var(--color-mute)]">{name}</span>
              <div className="h-1.5 rounded bg-[var(--color-panel-2)]">
                <div className="h-full rounded bg-[var(--color-accent)]" style={{ width: `${Math.min(100, v * 100)}%` }} />
              </div>
              <span className="num text-[var(--color-dim)]">{note}</span>
            </div>
          ))}
        </div>

        <div>
          <div className="label mb-2">Evidence timeline · click to replay that moment</div>
          <ol className="space-y-0.5">
            {evidence.map((e) => (
              <li key={e.event_id} onClick={() => onJump(e)} title="Jump the replay to 2 s before this"
                className="flex cursor-pointer items-center gap-2 rounded px-1 py-1 text-xs hover:bg-[var(--color-panel-2)]">
                <span className="num w-16 text-[var(--color-mute)]">{localTime(e.t)}</span>
                <span className="h-2 w-2 rounded-full" style={{ background: `var(--color-${e.source})` }} />
                <span className="w-28 text-[var(--color-mute)]">{SOURCE_LABEL[e.source]}</span>
                <span className="flex-1">{e.type.replaceAll('_', ' ')} <span className="text-[var(--color-dim)]">· {e.sensor_id}</span></span>
                <span className="num">{e.severity.toFixed(2)}</span>
                <span className="w-24 text-right text-[var(--color-dim)]">{PROVENANCE_LABEL[e.provenance]}</span>
              </li>
            ))}
          </ol>
        </div>
      </div>

      <div className="flex gap-2 border-t border-[var(--color-line)] p-3">
        <button disabled={busy} onClick={() => act('ack')} className="flex-1 rounded-md bg-[var(--color-panel-2)] py-2 text-sm hover:bg-[var(--color-line)]">Acknowledge</button>
        <button disabled={busy} onClick={() => act('escalate')} className="flex-1 rounded-md bg-[var(--color-high)] py-2 text-sm font-semibold text-black">Escalate</button>
        <button disabled={busy} onClick={() => act('dismiss')} className="flex-1 rounded-md bg-[var(--color-panel-2)] py-2 text-sm text-[var(--color-mute)] hover:bg-[var(--color-line)]">Dismiss</button>
      </div>
    </section>
  )
}
