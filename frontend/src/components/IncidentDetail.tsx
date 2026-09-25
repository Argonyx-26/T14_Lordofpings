import { ArrowUpRight, Check, CornerDownRight, ShieldAlert, X } from 'lucide-react'
import { useState } from 'react'
import { MOCK, PROVENANCE_LABEL, SOURCE_LABEL, localTime, post, scoreColor, severityLabel } from '../lib'
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
  const cfg = config ?? undefined

  if (!incident) {
    return (
      <section className="surface flex min-h-0 flex-col items-center justify-center gap-2 px-8 text-center">
        <ShieldAlert size={22} strokeWidth={1.25} className="text-[var(--color-fg-4)]" />
        <span className="display text-[24px] text-[var(--color-fg-2)]">No incident selected</span>
        <span className="max-w-64 text-[12px] text-[var(--color-fg-4)]">
          Choose an incident to see why it was raised, the evidence behind it, and what to do next.
        </span>
      </section>
    )
  }

  const act = async (action: 'ack' | 'escalate' | 'dismiss') => {
    if (MOCK || replayingLeadUp) return
    setBusy(true)
    try { await post(`/api/incidents/${incident.incident_id}/action`, { action, role }) } finally { setBusy(false) }
  }
  const color = scoreColor(incident.score, cfg)
  const b = incident.score_breakdown
  const factors: [string, string, number, string][] = [
    ['Severity', b.severity.toFixed(2), b.severity, 'strongest signal of each source, combined'],
    ['Confidence', b.confidence.toFixed(2), b.confidence, 'mean detector confidence'],
    ['Area criticality', b.criticality.toFixed(2), b.criticality, config?.areas[incident.area]?.name ?? incident.area],
    ['Corroboration', `×${b.corroboration}`, (b.corroboration - 1) / 0.45, `${incident.sources.length} independent source${incident.sources.length === 1 ? '' : 's'}`],
    ['Time of day', `×${b.time_factor}`, (b.time_factor - 1) / 0.3, b.time_factor > 1 ? 'night hours' : 'daytime'],
    ['Operator feedback', `×${b.feedback}`, 1 - b.feedback, b.feedback < 1 ? 'similar alerts were dismissed' : 'no dismissals'],
  ]
  const action = incident.brief ? config?.playbook[incident.brief.action_id] ?? incident.brief.action_id : null

  return (
    <section className="surface flex min-h-0 min-w-0 flex-col">
      <header className="shrink-0 px-5 pb-4 pt-4 hairline-b">
        <div className="flex items-center gap-2 text-[11px]">
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
          <span style={{ color }}>{incident.status === 'watch' ? 'Watch' : severityLabel(incident.score, cfg)}</span>
          <span className="text-[var(--color-fg-4)]">·</span>
          <span className="num text-[var(--color-fg-3)]">{incident.incident_id}</span>
          <span className="text-[var(--color-fg-4)]">·</span>
          <span className="capitalize text-[var(--color-fg-3)]">{incident.status === 'ack' ? 'acknowledged' : incident.status}</span>
          <span className="num ml-auto text-[var(--color-fg-3)]">since {localTime(incident.first_signal_at)}</span>
        </div>
        <div className="mt-3 flex items-end gap-4">
          <div className="flex items-baseline">
            <span className="display text-[64px]" style={{ color }}>{incident.score}</span>
            <span className="num ml-1 text-[12px] text-[var(--color-fg-4)]">/100</span>
          </div>
          <div className="min-w-0 pb-1.5">
            <h2 className="text-[17px] font-medium leading-snug text-[var(--color-fg)]">{incident.title.split(' — ')[0]}</h2>
            <p className="mt-0.5 text-[12px] text-[var(--color-fg-2)]">
              {config?.areas[incident.area]?.name ?? incident.area}
              {incident.common_cause && <span className="text-[var(--color-watch)]"> · likely common cause</span>}
            </p>
          </div>
        </div>
      </header>

      <div className="scroll min-h-0 flex-1 space-y-6 px-5 py-4">
        {replayingLeadUp && (
          <p className="rounded-md px-3 py-2 text-[12px] text-[var(--color-watch)]" style={{ boxShadow: 'inset 0 0 0 1px color-mix(in srgb, var(--color-watch) 45%, transparent)' }}>
            Replaying the lead-up. Press play and this incident re-forms as its evidence arrives.
          </p>
        )}

        {incident.brief && (
          <div>
            <div className="eyebrow mb-2">{incident.brief.generated_by === 'llm' ? 'Brief · written by Claude, checked against evidence' : 'Brief'}</div>
            <p className="text-[14px] leading-relaxed text-[var(--color-fg)]">{incident.brief.summary}</p>
            <p className="mt-1.5 text-[13px] leading-relaxed text-[var(--color-fg-2)]">{incident.brief.why}</p>
            {action && (
              <p className="mt-3 flex items-start gap-2 text-[13px] text-[var(--color-fg)]">
                <CornerDownRight size={14} strokeWidth={1.75} className="mt-0.5 shrink-0 text-[var(--color-fg-3)]" />
                {action}
              </p>
            )}
          </div>
        )}

        <div>
          <div className="eyebrow mb-2.5">Why this score</div>
          <div className="space-y-2">
            {factors.map(([name, value, level, note]) => (
              <div key={name} className="grid grid-cols-[112px_1fr_48px] items-center gap-3 text-[12px]">
                <span className="text-[var(--color-fg-2)]">{name}</span>
                <span className="flex min-w-0 flex-col gap-1">
                  <span className="h-[3px] rounded-full bg-[var(--color-surface-3)]">
                    <span className="block h-full rounded-full bg-[var(--color-fg-2)]" style={{ width: `${Math.max(0, Math.min(1, level)) * 100}%` }} />
                  </span>
                  <span className="truncate text-[10.5px] text-[var(--color-fg-4)]">{note}</span>
                </span>
                <span className="num text-right text-[var(--color-fg)]">{value}</span>
              </div>
            ))}
          </div>
        </div>

        <div>
          <div className="eyebrow mb-2.5">Evidence · click to replay the moment</div>
          <ol className="relative ml-1 border-l border-[var(--color-hair-2)]">
            {evidence.map((e) => (
              <li key={e.event_id}>
                <button onClick={() => onJump(e)} title="Replay from 2 s before this"
                  className="group relative flex w-full items-start gap-3 py-1.5 pl-4 pr-1 text-left">
                  <span className="absolute -left-[4.5px] top-[11px] h-2 w-2 rounded-full ring-2 ring-[var(--color-surface)]" style={{ background: `var(--color-${e.source})` }} />
                  <span className="num w-14 shrink-0 pt-px text-[11.5px] text-[var(--color-fg-3)]">{localTime(e.t)}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[12.5px] text-[var(--color-fg)] group-hover:underline group-hover:decoration-[var(--color-fg-4)] group-hover:underline-offset-2">
                      {e.type.replaceAll('_', ' ')}
                    </span>
                    <span className="block text-[11px] text-[var(--color-fg-3)]">
                      {SOURCE_LABEL[e.source]} · <span className="num">{e.sensor_id}</span> · {PROVENANCE_LABEL[e.provenance]}
                    </span>
                  </span>
                  <span className="num pt-px text-[11.5px] text-[var(--color-fg-2)]">{e.severity.toFixed(2)}</span>
                  <ArrowUpRight size={13} strokeWidth={1.75} className="mt-0.5 text-[var(--color-fg-4)] opacity-0 transition group-hover:opacity-100" />
                </button>
              </li>
            ))}
          </ol>
        </div>
      </div>

      <footer className="flex shrink-0 gap-2 px-5 py-3 hairline-t">
        <button disabled={busy} onClick={() => act('escalate')} className="btn btn-primary flex-1 justify-center">
          <ArrowUpRight size={14} strokeWidth={2} /> Escalate
        </button>
        <button disabled={busy} onClick={() => act('ack')} className="btn flex-1 justify-center">
          <Check size={14} strokeWidth={1.75} /> Acknowledge
        </button>
        <button disabled={busy} onClick={() => act('dismiss')} className="btn flex-1 justify-center">
          <X size={14} strokeWidth={1.75} /> Dismiss
        </button>
      </footer>
    </section>
  )
}
