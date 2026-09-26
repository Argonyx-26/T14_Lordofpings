import { Check, Copy, EyeOff, FileText, Link2, Printer, ShieldCheck, Waypoints, X } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { PROVENANCE_LABEL, SOURCE_LABEL, STATUS_LABEL, duration, eventLabel, localTime, modelName, severityLabel, track } from '../lib'
import type { ArgusEvent, Clock, Forecast, Incident, Intel, SiteConfigView } from '../types'
import type { AuditEntry } from './IncidentDetail'
import { Still, hasStill } from './Still'

interface Props {
  incident: Incident
  evidence: ArgusEvent[]
  config: SiteConfigView | null
  clock: Clock | null
  forecast: Forecast | null
  intel: Intel | null
  incidents: Record<string, Incident>
  decisions: AuditEntry[]
  verified: boolean
  onClose: () => void
}

interface Row { t: number; what: string; detail: string; kind: 'signal' | 'argus' | 'decision' | 'linked' }

const DECISION: Record<string, string> = { ack: 'Acknowledged', escalate: 'Escalated', dismiss: 'Dismissed', reopen: 'Reopened' }

/**
 * The case so far, as a report someone can hand over: assembled only from the incident, its evidence, the forecast,
 * the intel layer and the hash-chained decision log. Nothing in it is written by a model except the brief, which
 * says so. Print or save as PDF; or copy it as plain text for a message.
 */
export function CaseReport({ incident, evidence, config, clock, forecast, intel, incidents, decisions, verified, onClose }: Props) {
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onClose])

  const cfg = config ?? undefined
  const areaName = config?.areas[incident.area]?.name ?? incident.area
  const title = incident.title.split(' — ')[0]
  const series = intel?.series.find((s) => s.incidents.includes(incident.incident_id)) ?? null
  const links = intel?.links.filter((l) => l.from === incident.incident_id || l.to === incident.incident_id) ?? []
  const cov = intel?.coverage.areas.find((a) => a.area === incident.area)
  const b = incident.score_breakdown
  const cams = [...new Set(evidence.filter((e) => e.source === 'cctv').map((e) => e.sensor_id))]
  const stills = evidence.filter(hasStill).sort((a, z) => z.severity - a.severity).slice(0, 3)
  const next = forecast?.whatifs.find((w) => w.kind === 'next_stage')
  const best = forecast?.responses[0]
  const asOf = clock?.sim_t ?? incident.updated_at

  const rows: Row[] = [
    ...evidence.map((e) => ({ t: e.t, kind: 'signal' as const, what: eventLabel(e.type),
      detail: `${SOURCE_LABEL[e.source]} · ${config?.cameras[e.sensor_id]?.label ?? e.sensor_id} · strength ${e.severity.toFixed(2)} · ${e.attrs?.fixture ? 'placeholder, not a detection' : PROVENANCE_LABEL[e.provenance]}` })),
    ...(incident.opened_at ? [{ t: incident.opened_at, kind: 'argus' as const, what: 'ARGUS opened the incident for a person',
      detail: incident.decisive ? 'a decisive signal: goes to a person whatever the score' : `risk crossed ${config?.thresholds.open_threshold ?? 55}` }] : []),
    ...decisions.map((d) => ({ t: d.sim_t, kind: 'decision' as const, what: `${DECISION[d.action] ?? d.action} by ${d.role === 'supervisor' ? 'the supervisor' : 'the duty officer'}`,
      detail: [config?.playbook[d.note] ?? (d.note === 'false_alarm' ? 'marked as a false alarm' : d.note), `log entry ${d.hash.slice(0, 10)}`].filter(Boolean).join(' · ') })),
    ...(series ? series.incidents.filter((id) => id !== incident.incident_id && incidents[id]).map((id) => ({
      t: incidents[id].first_signal_at, kind: 'linked' as const, what: `Linked incident ${id}: ${incidents[id].title.split(' — ')[0]}`,
      detail: `${config?.areas[incidents[id].area]?.name ?? incidents[id].area} · ${links.find((l) => l.from === id || l.to === id)?.why ?? 'same series'}` })) : []),
  ].sort((a, z) => a.t - z.t)

  const text = [
    `ARGUS CASE REPORT · ${incident.incident_id} · ${config?.site_name ?? ''}`,
    `As of ${localTime(asOf)} (site time) · status: ${STATUS_LABEL[incident.status]} · risk ${incident.score} (peak ${incident.peak_score}), ${severityLabel(incident.score, cfg)}`,
    '', `WHAT: ${title}`, `WHERE: ${areaName}${cams.length ? ` (cameras ${cams.join(', ')})` : ''}`,
    `WHEN: ${localTime(incident.first_signal_at)} to ${localTime(incident.updated_at)} (${duration(incident.updated_at - incident.first_signal_at)})`,
    ...(incident.brief ? ['', `ASSESSMENT: ${incident.brief.summary}`, incident.brief.why] : []),
    '', 'TIMELINE', ...rows.map((r) => `  ${localTime(r.t)}  ${r.what} (${r.detail})`),
    '', `WHY THIS SCORE: severity ${b.severity.toFixed(2)} × confidence ${b.confidence.toFixed(2)} × area ${b.criticality.toFixed(2)} × corroboration ×${b.corroboration} × time ×${b.time_factor} × feedback ×${b.feedback} = ${b.score}`,
    ...(series ? ['', `PATTERN: ${series.title}`, ...links.map((l) => `  ${l.from} → ${l.to}: ${l.why}`), `  ${series.reading}`] : []),
    ...(cov ? ['', `WHAT ARGUS COULD SEE: ${cov.note}`] : []),
    ...(forecast?.script ? ['', `WHERE IT WAS HEADING: ${forecast.script.name}; ${next ? `${next.label.toLowerCase()}: risk ${next.score}` : 'no further stage'}`,
      ...(best ? [`  top-ranked response: ${best.label} (${best.why})`] : [])] : []),
    '', `DECISIONS: ${decisions.length ? decisions.map((d) => `${localTime(d.sim_t)} ${DECISION[d.action] ?? d.action} (${d.role})`).join('; ') : 'none yet'} · hash chain ${verified ? 'intact' : 'BROKEN'}`,
    '', 'Assembled by ARGUS from its event log. No face recognition; phone locations are area counts only.',
  ].join('\n')

  const copy = async () => {
    track('case_report_copy')
    try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1800) } catch { /* clipboard blocked */ }
  }

  return createPortal(
    <div className="case-report fixed inset-0 z-50 flex items-stretch justify-center bg-black/60 p-2 backdrop-blur-[2px] sm:p-5"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-label={`Case report ${incident.incident_id}`}
        className="case-sheet pop flex max-h-full w-full max-w-[880px] flex-col overflow-hidden rounded-2xl"
        style={{ background: 'var(--color-surface)', boxShadow: '0 30px 80px rgb(0 0 0 / .6), inset 0 0 0 1px var(--color-hair-2)' }}>
        <div className="no-print flex shrink-0 items-center gap-2 px-5 py-3 hairline-b">
          <FileText size={14} className="text-[var(--color-fg-3)]" />
          <span className="eyebrow">Case report · {incident.incident_id}</span>
          <span className="ml-auto" />
          <button className="btn btn-sm" onClick={copy}>{copied ? <Check size={13} /> : <Copy size={13} />} {copied ? 'Copied' : 'Copy as text'}</button>
          <button className="btn btn-sm btn-primary" onClick={() => { track('case_report_print'); window.print() }}><Printer size={13} /> Print / save PDF</button>
          <button onClick={onClose} className="btn btn-ghost btn-icon" aria-label="Close report"><X size={16} /></button>
        </div>

        <article className="scroll case-body min-h-0 flex-1 px-7 py-6 text-[12.5px] leading-relaxed text-[var(--color-fg-2)]">
          <header className="flex items-start gap-4 pb-4 hairline-b">
            <div className="min-w-0 flex-1">
              <div className="eyebrow">ARGUS case report · {config?.site_name}</div>
              <h1 className="display mt-1.5 text-[22px] text-[var(--color-fg)]">{title}</h1>
              <p className="mt-1 text-[12.5px]">
                {areaName}{cams.length > 0 && <> · cameras <span className="num">{cams.join(', ')}</span></>} ·{' '}
                <span className="num">{localTime(incident.first_signal_at)}–{localTime(incident.updated_at)}</span>
              </p>
            </div>
            <div className="shrink-0 text-right">
              <div className="figure text-[30px] text-[var(--color-fg)]">{incident.score}</div>
              <div className="text-[11px]">{severityLabel(incident.score, cfg)} · peak <span className="num">{incident.peak_score}</span></div>
              <div className="mt-1 text-[11px]">{STATUS_LABEL[incident.status]} · as of <span className="num">{localTime(asOf)}</span></div>
            </div>
          </header>

          {incident.brief && (
            <Block title="Assessment" note={incident.brief.generated_by === 'llm' ? `written by ${modelName(incident.brief.model)}, checked against the evidence` : 'from the scoring template'}>
              <p className="text-[13.5px] text-[var(--color-fg)]">{incident.brief.summary}</p>
              <p className="mt-1">{incident.brief.why}</p>
            </Block>
          )}

          {stills.length > 0 && (
            <div className="mt-5 grid grid-cols-3 gap-2">
              {stills.map((e) => (
                <Still key={e.event_id} e={e} className="aspect-video w-full" caption={
                  <span className="mt-1 block text-[10.5px] text-[var(--color-fg-3)]"><span className="num">{localTime(e.t)}</span> · {eventLabel(e.type)} · {e.sensor_id}</span>
                } />
              ))}
            </div>
          )}

          <Block title="Timeline" note={`${rows.length} entries · signals, ARGUS, decisions${series ? ', linked incidents' : ''}`}>
            <ol className="space-y-1">
              {rows.map((r, k) => (
                <li key={k} className="grid grid-cols-[64px_1fr] gap-2">
                  <span className="num text-[var(--color-fg-3)]">{localTime(r.t)}</span>
                  <span>
                    <span className={r.kind === 'decision' ? 'font-medium text-[var(--color-fg)]' : r.kind === 'argus' ? 'text-[var(--color-accent)]' : r.kind === 'linked' ? 'text-[var(--color-watch)]' : 'text-[var(--color-fg)]'}>{r.what}</span>
                    <span className="block text-[11px] text-[var(--color-fg-3)]">{r.detail}</span>
                  </span>
                </li>
              ))}
            </ol>
          </Block>

          <Block title="Why this score" note="score = 100 × S × (0.5 + 0.5·C) × K × R × T × F">
            <p className="num text-[12px] text-[var(--color-fg)]">
              {b.severity.toFixed(2)} × (0.5 + 0.5·{b.confidence.toFixed(2)}) × {b.criticality.toFixed(2)} × {b.corroboration} × {b.time_factor} × {b.feedback} → {b.score}
            </p>
            <p className="mt-1 text-[11.5px]">
              Severity from the strongest signal of each of {incident.sources.length} source{incident.sources.length === 1 ? '' : 's'} ({incident.sources.map((s) => SOURCE_LABEL[s]).join(', ')});
              corroboration ×{b.corroboration}; {b.feedback < 1 ? 'similar alerts here were dismissed before' : 'no dismissals of similar alerts'}.
            </p>
          </Block>

          {series && (
            <Block title="Pattern" icon={<Waypoints size={11} />} note="linked by behaviour, place and time; never by identity">
              <p className="text-[var(--color-fg)]">{series.title}</p>
              <ul className="mt-1 space-y-0.5 text-[11.5px]">
                {links.map((l) => <li key={l.from + l.to}><span className="num">{l.from} → {l.to}</span>: {l.why}</li>)}
              </ul>
              <p className="mt-1 text-[11px] text-[var(--color-fg-3)]">{series.reading}</p>
            </Block>
          )}

          {cov && (
            <Block title="What ARGUS could and could not see" icon={<EyeOff size={11} />}>
              <p>{cov.note}.</p>
              {cov.ceiling.corroboration !== null && (
                <p className="mt-0.5 text-[11.5px] text-[var(--color-fg-3)]">
                  {incident.sources.filter((s) => cov.streams[s as 'cctv']).length} of {cov.ceiling.sources} streams covering this area agreed; the most corroboration it can give is ×{cov.ceiling.corroboration}.
                </p>
              )}
            </Block>
          )}

          {forecast?.script && (
            <Block title="Where it was heading" note={forecast.script.name.toLowerCase()}>
              <p>
                Stages: {forecast.script.stages.map((s) => `${s.label}${s.state === 'done' ? ' ✓' : s.state === 'next' ? ' (next)' : ''}`).join(' → ')}.
                {next && <> {next.label}: risk <span className="num">{forecast.base.score} → {next.score}</span>.</>}
              </p>
              {best && <p className="mt-0.5 text-[11.5px] text-[var(--color-fg-3)]">Top-ranked response: <span className="text-[var(--color-fg-2)]">{best.label}</span> ({best.why}).</p>}
            </Block>
          )}

          <Block title="Decisions and integrity" icon={verified ? <ShieldCheck size={11} /> : <Link2 size={11} />}>
            {decisions.length ? (
              <ul className="space-y-0.5">
                {decisions.map((d) => (
                  <li key={d.hash}><span className="num">{localTime(d.sim_t)}</span> · {DECISION[d.action] ?? d.action} by {d.role === 'supervisor' ? 'the supervisor' : 'the duty officer'}
                    {d.note && config?.playbook[d.note] ? `: ${config.playbook[d.note]}` : ''} · <span className="num text-[var(--color-fg-3)]">{d.hash.slice(0, 16)}</span></li>
                ))}
              </ul>
            ) : <p>No decision recorded yet.</p>}
            <p className="mt-1 text-[11.5px]" style={{ color: verified ? 'var(--color-ok)' : 'var(--color-crit)' }}>
              {verified ? 'Hash chain intact: no decision has been altered since it was made.' : 'Hash chain broken: the log was edited.'}
            </p>
          </Block>

          <p className="mt-6 pt-3 text-[10.5px] text-[var(--color-fg-4)] hairline-t">
            Assembled by ARGUS from its event log and decision log. Scores, links and forecasts are computed by stated rules, not by a model.
            No face recognition; people are anonymous tracks within one camera; phone locations are counts per area. {config?.attribution}
          </p>
        </article>
      </div>
    </div>,
    document.body,
  )
}

function Block({ title, note, icon, children }: { title: string; note?: string; icon?: ReactNode; children: ReactNode }) {
  return (
    <section className="mt-5 break-inside-avoid">
      <div className="eyebrow mb-1.5 flex items-center gap-1.5">{icon}{title}{note && <span className="font-normal normal-case tracking-normal text-[var(--color-fg-4)]">· {note}</span>}</div>
      {children}
    </section>
  )
}
