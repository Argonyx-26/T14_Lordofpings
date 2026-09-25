import { ArrowUpRight, ChevronRight, Cpu, CornerDownRight, Eye, Link2, Radar, ShieldCheck, UserCheck } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import {
  API, LEVEL_COLOR, MOCK, PROVENANCE_LABEL, SOURCE_LABEL, STATUS_LABEL, duration, eventLabel, fmt, levelOf, localTime, modelName, post, severityLabel,
} from '../lib'
import type { ArgusEvent, Clock, Incident, SiteConfigView, Summary } from '../types'
import { ResponseMenu, type Action } from './ResponseMenu'
import { Still, hasStill } from './Still'
import { SourceIcon, StatusSymbol } from './Symbols'
import type { Role } from './TopBar'

interface Props {
  incident: Incident | null
  auto: boolean
  config: SiteConfigView | null
  clock: Clock | null
  summary: Summary | null
  role: Role
  evidence: ArgusEvent[]
  onJump: (e: ArgusEvent) => void
  replayingLeadUp?: boolean
}

interface AuditEntry { incident_id: string; action: Action; role: Role; note: string; sim_t: number; score: number; hash: string }

export function IncidentDetail({ incident, auto, config, clock, summary, role, evidence, onJump, replayingLeadUp }: Props) {
  const cfg = config ?? undefined
  const log = useAudit(incident, clock)

  if (!incident) return <HowItWorks config={config} summary={summary} />

  const act = async (action: Action, note: string) => {
    await post(`/api/incidents/${incident.incident_id}/action`, { action, role, note })
    log.refresh()
  }
  const level = incident.status === 'watch' ? 'watch' : levelOf(incident.score, cfg)
  const color = LEVEL_COLOR[level]
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
  const keyFrame = evidence.filter(hasStill).reduce<ArgusEvent | null>((a, e) => (!a || e.severity > a.severity ? e : a), null)
  const cams = [...new Set(evidence.filter((e) => e.source === 'cctv').map((e) => e.sensor_id))]
  const decision = log.entries[0]

  return (
    <section className="surface fill-sm flex min-h-0 min-w-0 flex-1 flex-col">
      <header key={incident.incident_id} className="fade-in shrink-0 px-4 pb-4 pt-3.5 hairline-b">
        <div className="flex items-center gap-2 text-[11.5px]">
          <StatusSymbol level={level} size={10} pulse={incident.status === 'open'} />
          <span className="font-medium" style={{ color }}>{incident.status === 'watch' ? 'Watch' : severityLabel(incident.score, cfg)}</span>
          <span className="num text-[var(--color-fg-3)]">{incident.incident_id}</span>
          {auto && <span className="chip" title="Nothing selected, so the most urgent incident is shown">Most urgent</span>}
          <span className="num ml-auto text-[var(--color-fg-3)]">since {localTime(incident.first_signal_at)}</span>
        </div>
        <div className="mt-3 flex items-center gap-3.5">
          <ScoreRing score={incident.score} color={color} config={config} />
          <div className="min-w-0">
            <h2 className="text-[17px] font-semibold leading-snug tracking-[-0.01em] text-[var(--color-fg)]">{incident.title.split(' — ')[0]}</h2>
            <p className="mt-0.5 text-[12px] text-[var(--color-fg-2)]">
              {config?.areas[incident.area]?.name ?? incident.area}
              {cams.length > 0 && <span className="text-[var(--color-fg-3)]"> · seen on <span className="num">{cams.join(', ')}</span></span>}
              {incident.common_cause && <span className="text-[var(--color-watch)]"> · likely common cause</span>}
            </p>
          </div>
        </div>
        <Progress incident={incident} clock={clock} decision={decision} />
      </header>

      <div className="scroll min-h-0 flex-1 space-y-5 px-4 py-4">
        {replayingLeadUp && (
          <p className="rounded-lg px-3 py-2 text-[12px] leading-relaxed text-[var(--color-watch)]" style={{ background: 'color-mix(in srgb, var(--color-watch) 9%, transparent)' }}>
            Replaying the lead-up. Press play and this incident re-forms as its evidence arrives.
          </p>
        )}

        {incident.brief && (
          <div>
            <div className="eyebrow mb-2 flex items-center gap-1.5">
              <Cpu size={11} strokeWidth={2} /> ARGUS assessment
              <span className="font-normal normal-case tracking-normal text-[var(--color-fg-4)]">
                · {incident.brief.generated_by === 'llm' ? `written by ${modelName(incident.brief.model)}, checked against the evidence` : 'from the scoring template'}
              </span>
            </div>
            <p className="text-[14px] leading-relaxed text-[var(--color-fg)]">{incident.brief.summary}</p>
            <p className="mt-1.5 text-[12.5px] leading-relaxed text-[var(--color-fg-2)]">{incident.brief.why}</p>
            {action && (
              <div className="mt-3 flex items-start gap-2.5 rounded-lg px-3 py-2.5" style={{ background: 'var(--color-surface-2)', boxShadow: 'inset 0 0 0 1px var(--color-hair-2)' }}>
                <CornerDownRight size={14} strokeWidth={2} className="mt-0.5 shrink-0 text-[var(--color-accent)]" />
                <span>
                  <span className="eyebrow block">Recommended</span>
                  <span className="text-[13px] text-[var(--color-fg)]">{action}</span>
                </span>
              </div>
            )}
          </div>
        )}

        <div>
          <div className="eyebrow mb-2.5">Evidence · click to replay the moment</div>
          {keyFrame && (
            <button key={keyFrame.event_id} onClick={() => onJump(keyFrame)} title="Replay from 2 s before this"
              className="group block w-full text-left">
              <Still e={keyFrame} className="aspect-video w-full" caption={
                <span className="mt-1 block text-[11px] text-[var(--color-fg-3)]">
                  <span className="num">{localTime(keyFrame.t)}</span> · {eventLabel(keyFrame.type)} ·{' '}
                  {config?.cameras[keyFrame.sensor_id]?.label ?? keyFrame.sensor_id}
                  <span className="opacity-0 transition group-hover:opacity-100"> · replay</span>
                </span>
              } />
            </button>
          )}
          <ol className="relative ml-1.5 border-l border-[var(--color-hair-2)]">
            {evidence.map((e) => (
              <li key={e.event_id}>
                <button onClick={() => onJump(e)} title="Replay from 2 s before this"
                  className="group relative flex w-full items-start gap-2.5 rounded-r-md py-1.5 pl-4 pr-1 text-left transition hover:bg-[var(--color-surface-2)]">
                  <span className="absolute -left-[7px] top-[7px] flex h-[13px] w-[13px] items-center justify-center rounded-full bg-[var(--color-surface)]">
                    <SourceIcon source={e.source} size={11} />
                  </span>
                  <span className="num w-[58px] shrink-0 pt-px text-[11.5px] text-[var(--color-fg-3)]">{localTime(e.t)}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[12.5px] text-[var(--color-fg)]">{eventLabel(e.type)}</span>
                    <span className="block truncate text-[11px] text-[var(--color-fg-3)]">
                      {SOURCE_LABEL[e.source]} · <span className="num">{e.sensor_id}</span> · {PROVENANCE_LABEL[e.provenance]}
                    </span>
                  </span>
                  {hasStill(e) && <Still key={e.event_id} e={e} className="h-[36px] w-[64px] shrink-0" />}
                  <Strength value={e.severity} />
                </button>
              </li>
            ))}
          </ol>
        </div>

        <Section title="Why this score" hint={`${incident.sources.length} source${incident.sources.length === 1 ? '' : 's'} · ${factors.length} factors`}>
          {incident.decisive && (
            <p className="mb-3 text-[12px] leading-relaxed text-[var(--color-fg-2)]">
              <span className="text-[var(--color-fg)]">Opened at once:</span> an object left behind by someone who has
              walked out of view always goes to a person, whatever the score.
            </p>
          )}
          <div className="space-y-2">
            {factors.map(([name, value, lvl, note]) => (
              <div key={name} className="grid grid-cols-[108px_1fr_44px] items-center gap-3 text-[12px]">
                <span className="text-[var(--color-fg-2)]">{name}</span>
                <span className="flex min-w-0 flex-col gap-1">
                  <span className="h-[3px] rounded-full bg-[var(--color-surface-3)]">
                    <span className="block h-full rounded-full bg-[var(--color-fg-2)]" style={{ width: `${Math.max(0, Math.min(1, lvl)) * 100}%` }} />
                  </span>
                  <span className="truncate text-[10.5px] text-[var(--color-fg-4)]">{note}</span>
                </span>
                <span className="num text-right text-[var(--color-fg)]">{value}</span>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Decision log" hint={log.entries.length ? `${log.entries.length} decision${log.entries.length > 1 ? 's' : ''} · ${log.verified ? 'chain verified' : 'chain broken'}` : 'no decisions yet'}
          open={log.entries.length > 0}>
          {log.entries.length === 0 ? (
            <p className="text-[12px] leading-relaxed text-[var(--color-fg-3)]">
              Nothing decided yet. Every decision is appended to a hash-chained log, so it can't be quietly edited later.
            </p>
          ) : (
            <>
              <ul className="space-y-2">
                {log.entries.map((a) => (
                  <li key={a.hash} className="flex items-start gap-2.5 text-[12px]">
                    <UserCheck size={13} strokeWidth={1.75} className="mt-0.5 shrink-0 text-[var(--color-fg-3)]" />
                    <span className="min-w-0 flex-1">
                      <span className="text-[var(--color-fg)]">{STATUS_LABEL[a.action === 'ack' ? 'ack' : a.action === 'escalate' ? 'escalated' : 'dismissed']}</span>
                      <span className="text-[var(--color-fg-3)]"> by {a.role === 'supervisor' ? 'Supervisor' : 'Duty officer'}</span>
                      {a.note && config?.playbook[a.note] && <span className="block text-[11.5px] text-[var(--color-fg-2)]">{config.playbook[a.note]}</span>}
                      {a.note === 'false_alarm' && <span className="block text-[11.5px] text-[var(--color-fg-2)]">Marked as a false alarm</span>}
                    </span>
                    <span className="num text-[11px] text-[var(--color-fg-3)]">{localTime(a.sim_t)}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-2.5 flex items-center gap-1.5 text-[11px] text-[var(--color-fg-3)]">
                {log.verified ? <ShieldCheck size={12} className="text-[var(--color-ok)]" /> : <Link2 size={12} className="text-[var(--color-crit)]" />}
                {log.verified ? 'Hash chain intact: no entry has been altered' : 'Hash chain broken: the log was edited'}
              </p>
            </>
          )}
        </Section>
      </div>

      <footer className="flex shrink-0 items-center gap-3 px-4 py-3 hairline-t">
        <ResponseMenu incident={incident} config={config} onAct={act}
          disabled={MOCK || !!replayingLeadUp} disabledReason={MOCK ? 'Needs the backend' : 'Wait for the incident to re-form'} />
      </footer>
    </section>
  )
}

/** Signals → opened by ARGUS → a person decides. Who did what, and when. */
function Progress({ incident, clock, decision }: { incident: Incident; clock: Clock | null; decision?: AuditEntry }) {
  const decided = ['ack', 'escalated', 'dismissed'].includes(incident.status)
  const waiting = clock && incident.opened_at && !decided ? clock.sim_t - incident.opened_at : null
  const steps: { label: string; sub: ReactNode; state: 'done' | 'now' | 'todo'; Icon: typeof Radar }[] = [
    { label: 'Signals', sub: <span className="num">{localTime(incident.first_signal_at)}</span>, state: 'done', Icon: Radar },
    {
      label: incident.opened_at ? 'Opened by ARGUS' : incident.status === 'watch' ? 'On watch' : 'Building',
      sub: incident.opened_at ? <span className="num">{localTime(incident.opened_at)}</span> : 'below the bar for a person',
      state: incident.opened_at ? 'done' : 'now', Icon: Cpu,
    },
    {
      label: decided ? STATUS_LABEL[incident.status] : 'Your decision',
      sub: decided
        ? (decision ? <>{decision.role === 'supervisor' ? 'Supervisor' : 'Duty officer'} · <span className="num">{localTime(decision.sim_t)}</span></> : 'by a person')
        : waiting !== null ? <>waiting <span className="num">{duration(waiting)}</span></> : 'not needed yet',
      state: decided ? 'done' : incident.opened_at ? 'now' : 'todo', Icon: Eye,
    },
  ]
  return (
    <ol className="mt-3.5 grid grid-cols-3 gap-2" aria-label="Response progress">
      {steps.map((s, k) => (
        <li key={k} className="relative">
          <div className="flex items-center gap-1.5">
            <span className={`flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full ${s.state === 'now' ? 'breathe' : ''}`}
              style={{
                background: s.state === 'done' ? 'var(--color-fg)' : 'transparent',
                boxShadow: s.state === 'done' ? undefined : `inset 0 0 0 1.5px ${s.state === 'now' ? 'var(--color-accent)' : 'var(--color-fg-4)'}`,
                color: s.state === 'done' ? '#0a0c0f' : s.state === 'now' ? 'var(--color-accent)' : 'var(--color-fg-4)',
              }}>
              <s.Icon size={10} strokeWidth={2.4} />
            </span>
            {k < steps.length - 1 && <span className="h-px flex-1" style={{ background: s.state === 'done' ? 'var(--color-fg-3)' : 'var(--color-hair-2)' }} />}
          </div>
          <div className={`mt-1.5 truncate text-[11.5px] ${s.state === 'todo' ? 'text-[var(--color-fg-4)]' : 'text-[var(--color-fg)]'}`}>{s.label}</div>
          <div className="truncate text-[10.5px] text-[var(--color-fg-3)]">{s.sub}</div>
        </li>
      ))}
    </ol>
  )
}

/** Risk score as a gauge with the "watch" and "open for a person" thresholds marked on it. */
function ScoreRing({ score, color, config }: { score: number; color: string; config: SiteConfigView | null }) {
  const r = 24
  const c = 2 * Math.PI * r
  const tick = (v: number) => {
    const a = (v / 100) * 2 * Math.PI - Math.PI / 2
    return { x1: 28 + (r - 5) * Math.cos(a), y1: 28 + (r - 5) * Math.sin(a), x2: 28 + (r + 5) * Math.cos(a), y2: 28 + (r + 5) * Math.sin(a) }
  }
  return (
    <div className="relative h-14 w-14 shrink-0" title={`Risk ${score} of 100`}>
      <svg viewBox="0 0 56 56" className="h-14 w-14">
        <circle cx="28" cy="28" r={r} fill="none" stroke="var(--color-surface-3)" strokeWidth="4" />
        <circle cx="28" cy="28" r={r} fill="none" stroke={color} strokeWidth="4" strokeLinecap="round"
          strokeDasharray={`${(score / 100) * c} ${c}`} transform="rotate(-90 28 28)" style={{ transition: 'stroke-dasharray .6s ease-out' }} />
        {[config?.thresholds.watch_threshold ?? 35, config?.thresholds.open_threshold ?? 55].map((v) => (
          <line key={v} {...tick(v)} stroke="var(--color-bg)" strokeWidth="1.5" />
        ))}
      </svg>
      <span className="figure absolute inset-0 flex items-center justify-center text-[19px] text-[var(--color-fg)]">{score}</span>
    </div>
  )
}

/** Signal strength (0-1) as a small meter rather than a bare decimal. */
function Strength({ value }: { value: number }) {
  return (
    <span className="mt-1.5 flex shrink-0 gap-[2px]" title={`Signal strength ${value.toFixed(2)}`}>
      {[0.25, 0.5, 0.75].map((t) => (
        <span key={t} className="h-2.5 w-[3px] rounded-full" style={{ background: value >= t ? 'var(--color-fg-2)' : 'var(--color-surface-4)' }} />
      ))}
    </span>
  )
}

function Section({ title, hint, open, children }: { title: string; hint: string; open?: boolean; children: ReactNode }) {
  return (
    <details open={open} className="group rounded-lg" style={{ boxShadow: 'inset 0 0 0 1px var(--color-hair)' }}>
      <summary className="flex items-center gap-2 px-3 py-2.5 transition hover:bg-[var(--color-surface-2)]">
        <ChevronRight size={13} className="chev shrink-0 text-[var(--color-fg-3)]" />
        <span className="whitespace-nowrap text-[12.5px] text-[var(--color-fg)]">{title}</span>
        <span className="ml-auto truncate text-[11px] text-[var(--color-fg-3)]">{hint}</span>
      </summary>
      <div className="px-3 pb-3 pt-1">{children}</div>
    </details>
  )
}

/**
 * Decisions on this incident from the hash-chained audit log. The log outlives a replay reset (ids repeat), so
 * only decisions consistent with this run are shown: none while the incident is still undecided, and none from
 * later in the recording than the clock has reached.
 */
function useAudit(incident: Incident | null, clock: Clock | null) {
  const [data, setData] = useState<{ verified: boolean; entries: AuditEntry[] }>({ verified: true, entries: [] })
  const [n, setN] = useState(0)
  const id = incident?.incident_id
  const status = incident?.status
  useEffect(() => {
    if (!id || MOCK) return
    let stale = false
    fetch(`${API}/api/audit`).then((r) => r.json()).then((d) => { if (!stale) setData(d) }).catch(() => {})
    return () => { stale = true }
  }, [id, status, n])
  const decided = status === 'ack' || status === 'escalated' || status === 'dismissed'
  const entries = !incident || !decided ? [] : data.entries
    .filter((a) => a.incident_id === incident.incident_id && a.sim_t >= incident.first_signal_at && (!clock || a.sim_t <= clock.sim_t + 1))
    .reverse().slice(0, 5)
  return { verified: data.verified, entries, refresh: () => setN((k) => k + 1) }
}

/** Nothing selected and nothing urgent: explain what ARGUS is doing, in the order a judge would ask. */
function HowItWorks({ config, summary }: { config: SiteConfigView | null; summary: Summary | null }) {
  const by = summary?.by_source ?? {}
  const steps = [
    { Icon: Radar, title: 'Sense', body: <>Cameras, door sensors and phone locations stream in: <span className="num text-[var(--color-fg)]">{fmt(summary?.raw_events)}</span> signals so far.</> },
    { Icon: Eye, title: 'Detect', body: <>Off-the-shelf YOLO and tracking turn footage into events a person would care about: a bag left behind, a bag taken, someone running, a crowd forming.</> },
    { Icon: Cpu, title: 'Fuse', body: <>Signals that share a place and a few minutes become one incident, scored for risk and explained in plain words.</> },
    { Icon: UserCheck, title: 'Decide', body: <>A person acknowledges, escalates or dismisses. Every decision is logged, and dismissals teach ARGUS what to ignore.</> },
  ]
  return (
    <section className="surface fill-sm flex min-h-0 flex-1 flex-col">
      <div className="scroll flex-1 px-5 py-5">
        <div className="flex items-center gap-2">
          <StatusSymbol level="clear" size={11} />
          <span className="eyebrow" style={{ color: 'var(--color-ok)' }}>All clear · nothing to decide</span>
        </div>
        <h2 className="display mt-2 text-[22px] text-[var(--color-fg)]">How ARGUS works</h2>
        <p className="mt-1.5 text-[12.5px] leading-relaxed text-[var(--color-fg-2)]">
          ARGUS is watching {Object.keys(config?.cameras ?? {}).length} cameras across {Object.keys(config?.areas ?? {}).length} areas
          and absorbing routine activity. When signals agree, the incident appears here with the footage, the evidence and a recommended response.
        </p>
        <ol className="mt-5 space-y-4">
          {steps.map((s, k) => (
            <li key={s.title} className="flex gap-3">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg" style={{ background: 'var(--color-surface-3)' }}>
                <s.Icon size={14} strokeWidth={1.75} className="text-[var(--color-fg-2)]" />
              </span>
              <span>
                <span className="text-[13px] font-medium text-[var(--color-fg)]"><span className="num text-[var(--color-fg-4)]">{k + 1}</span> {s.title}</span>
                <span className="mt-0.5 block text-[12px] leading-relaxed text-[var(--color-fg-3)]">{s.body}</span>
              </span>
            </li>
          ))}
        </ol>
        <div className="mt-5 flex flex-wrap gap-x-4 gap-y-1.5">
          {Object.entries(by).map(([src, n]) => (
            <span key={src} className="flex items-center gap-1.5 text-[11.5px] text-[var(--color-fg-3)]">
              <SourceIcon source={src} /> {SOURCE_LABEL[src]} <span className="num text-[var(--color-fg-2)]">{fmt(n)}</span>
            </span>
          ))}
        </div>
        <p className="mt-5 flex items-center gap-1.5 text-[11.5px] text-[var(--color-fg-4)]">
          <ArrowUpRight size={12} /> Press play, or pick a staged scenario on the timeline.
        </p>
      </div>
    </section>
  )
}
