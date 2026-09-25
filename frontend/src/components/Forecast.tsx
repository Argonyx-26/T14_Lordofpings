import { Ambulance, ArrowRight, Cctv, Check, ChevronRight, Clock3, Footprints, LoaderCircle, Route, Siren, Users, X } from 'lucide-react'
import { useEffect, useState, type ComponentType } from 'react'
import { LEVEL_COLOR, duration, eventLabel, localTime, type Level } from '../lib'
import type { Clock, Forecast, Incident, ResponseOption, ScriptStage, WhatIf } from '../types'
import { StatusSymbol } from './Symbols'

const LEVEL_WORD: Record<string, string> = { critical: 'Critical', high: 'High', watch: 'Watch', low: 'Low' }
const RESPONDER: Record<string, { Icon: ComponentType<{ size?: number; strokeWidth?: number; className?: string }>; word: string }> = {
  camera: { Icon: Cctv, word: 'Cameras' },
  guard: { Icon: Footprints, word: 'Guard' },
  staff: { Icon: Users, word: 'Staff' },
  police: { Icon: Siren, word: 'Police' },
  medical: { Icon: Ambulance, word: 'Medical' },
}
const mmss = (s: number) => duration(s)

/** Seconds left in the evidence window, live against the replay clock when there is one. */
function windowLeft(fc: Forecast, clock: Clock | null): number {
  return clock ? Math.max(0, Math.round(fc.window.closes_at - clock.sim_t)) : fc.window.remaining_s
}

/** Compact card in the incident panel: the script stage, the likeliest next step and its score, the window. */
export function ForecastCard({ fc, clock, onPlan }: { fc: Forecast; clock: Clock | null; onPlan: () => void }) {
  const next = fc.whatifs.find((w) => w.kind === 'next_stage')
  const left = windowLeft(fc, clock)
  return (
    <div className="rounded-lg" style={{ boxShadow: 'inset 0 0 0 1px var(--color-hair-2)' }}>
      <div className="px-3 pb-3 pt-2.5">
        <div className="eyebrow flex items-center gap-1.5">
          <Route size={11} strokeWidth={2} /> Where this is heading
          {fc.script && <span className="font-normal normal-case tracking-normal text-[var(--color-fg-4)]">· {fc.script.name.toLowerCase()}</span>}
        </div>
        {fc.script && <StageStrip stages={fc.script.stages} />}
        {next ? (
          <p className="mt-2.5 text-[12.5px] leading-relaxed text-[var(--color-fg-2)]">
            {next.label}: risk <span className="num text-[var(--color-fg)]">{fc.base.score}</span>
            <ArrowRight size={11} className="mx-1 inline text-[var(--color-fg-3)]" />
            <span className="num font-medium" style={{ color: LEVEL_COLOR[next.level as Level] }}>{next.score}</span>{' '}
            <span style={{ color: LEVEL_COLOR[next.level as Level] }}>{LEVEL_WORD[next.level]}</span>
            {next.title_changes && <> and it becomes <span className="text-[var(--color-fg)]">"{next.title}"</span></>}.
          </p>
        ) : (
          <p className="mt-2 text-[12.5px] text-[var(--color-fg-3)]">No known escalation path from these signals; see what else would change the score.</p>
        )}
        <p className="mt-1.5 flex items-center gap-1.5 text-[11px] text-[var(--color-fg-3)]">
          <Clock3 size={11} />
          {left > 0 ? <>Evidence window open for <span className="num text-[var(--color-fg-2)]">{mmss(left)}</span>: new signals here join this incident</>
            : 'Evidence window closed: new signals here start a fresh incident'}
        </p>
      </div>
      <button onClick={onPlan} className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12.5px] font-medium text-[var(--color-fg)] transition hairline-t hover:bg-[var(--color-surface-2)]">
        Plan the response
        <span className="text-[11px] font-normal text-[var(--color-fg-3)]">
          {fc.whatifs.length} what-ifs · {fc.responses.length} responses compared
        </span>
        <ChevronRight size={14} className="ml-auto text-[var(--color-fg-3)]" />
      </button>
    </div>
  )
}

function StageStrip({ stages }: { stages: ScriptStage[] }) {
  return (
    <ol className="mt-2.5 flex items-start gap-1" aria-label="Script stages">
      {stages.map((s, k) => (
        <li key={s.id} className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="h-[3px] rounded-full" style={{
            background: s.state === 'done' ? 'var(--color-fg-2)' : s.state === 'next' ? 'var(--color-accent)' : 'var(--color-surface-4)',
          }} />
          <span className={`truncate text-[10.5px] ${s.state === 'done' ? 'text-[var(--color-fg-2)]' : s.state === 'next' ? 'text-[var(--color-accent)]' : 'text-[var(--color-fg-4)]'}`}
            title={s.label}>
            {k + 1}. {s.label}
          </span>
        </li>
      ))}
    </ol>
  )
}

/** A 0-100 score on the site's bands: the projected value, the current one, and the watch / open / critical lines. */
function ScoreBar({ value, base, th, lvl }: { value: number; base: number; th: Forecast['thresholds']; lvl: string }) {
  return (
    <div className="relative h-2 w-full rounded-full bg-[var(--color-surface-3)]" role="img" aria-label={`risk ${value} of 100`}>
      <div className="absolute inset-y-0 left-0 rounded-full transition-all" style={{ width: `${Math.min(100, value)}%`, background: LEVEL_COLOR[lvl as Level], opacity: 0.85 }} />
      {[th.watch, th.open, th.critical].map((t) => (
        <span key={t} className="absolute -top-0.5 h-3 w-px bg-[var(--color-bg)]" style={{ left: `${t}%` }} />
      ))}
      <span className="absolute -top-1 h-4 w-[2px] rounded-full bg-[var(--color-fg)]" style={{ left: `calc(${Math.min(100, base)}% - 1px)` }} title={`now ${base}`} />
    </div>
  )
}

const GROUPS: { kind: WhatIf['kind'][]; title: string }[] = [
  { kind: ['next_stage'], title: 'If it escalates' },
  { kind: ['corroborate'], title: 'If another sensor agrees' },
  { kind: ['night', 'profile'], title: 'Context that changes the bar' },
  { kind: ['dismiss'], title: 'If you dismiss' },
]

interface PlannerProps {
  fc: Forecast
  incident: Incident
  clock: Clock | null
  areaName: string
  onClose: () => void
  onApply?: (r: ResponseOption) => Promise<void>
  applyDisabled?: string | null
}

/**
 * The response planner: how incidents like this unfold (crime script), what would change the score (each one the
 * real scorer on real evidence plus one hypothetical signal), and a course-of-action comparison you can simulate
 * and apply. Nothing on it is decided by a model.
 */
export function ResponsePlanner({ fc, incident, clock, areaName, onClose, onApply, applyDisabled }: PlannerProps) {
  const [pick, setPick] = useState<string>(fc.responses[0]?.action ?? '')
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState<string | null>(null)
  const chosen = fc.responses.find((r) => r.action === pick) ?? null
  const left = windowLeft(fc, clock)
  const lvl = fc.base.level
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-center bg-black/60 p-2 backdrop-blur-[2px] sm:p-5" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-label="Response planner"
        className="pop flex max-h-full w-full max-w-[1320px] flex-col overflow-hidden rounded-2xl"
        style={{ background: 'var(--color-surface)', boxShadow: '0 30px 80px rgb(0 0 0 / .6), inset 0 0 0 1px var(--color-hair-2)' }}>
        {/* header */}
        <div className="flex shrink-0 items-center gap-3 px-5 py-3.5 hairline-b">
          <StatusSymbol level={lvl as Level} size={11} />
          <div className="min-w-0">
            <div className="eyebrow">Response planner · {incident.incident_id} · {areaName}</div>
            <div className="truncate text-[16px] font-semibold tracking-[-0.01em]">{fc.base.title || incident.title.split(' — ')[0]}</div>
          </div>
          <div className="ml-auto hidden items-center gap-4 text-[11.5px] text-[var(--color-fg-3)] md:flex">
            <span>risk now <span className="figure text-[18px] text-[var(--color-fg)]">{fc.base.score}</span></span>
            <span className="flex items-center gap-1"><Clock3 size={12} /> {left > 0 ? <>window <span className="num text-[var(--color-fg-2)]">{mmss(left)}</span></> : 'window closed'}</span>
            {fc.context.people_in_area !== null && <span className="flex items-center gap-1"><Users size={12} /> <span className="num text-[var(--color-fg-2)]">{fc.context.people_in_area}</span> phones in the area</span>}
          </div>
          <button onClick={onClose} className="btn btn-ghost btn-icon ml-2" aria-label="Close planner"><X size={16} /></button>
        </div>

        <div className="grid min-h-0 flex-1 grid-cols-1 overflow-y-auto lg:grid-cols-[minmax(0,0.82fr)_minmax(0,1.08fr)_minmax(0,1.5fr)] lg:overflow-hidden">
          {/* 1 · how this unfolds */}
          <section className="flex min-h-0 flex-col" style={{ borderRight: '1px solid var(--color-hair)' }}>
            <Head n={1} title="How this unfolds" note={fc.script ? fc.script.name : 'no known script'} />
            <div className="scroll min-h-0 flex-1 px-5 pb-5">
              {fc.script ? (
                <ol className="relative ml-2 border-l border-[var(--color-hair-2)]">
                  {fc.script.stages.map((s) => (
                    <li key={s.id} className="relative pb-4 pl-5 last:pb-0">
                      <span className="absolute -left-[7px] top-0.5 flex h-[13px] w-[13px] items-center justify-center rounded-full"
                        style={{
                          background: s.state === 'done' ? 'var(--color-fg)' : 'var(--color-surface)',
                          boxShadow: s.state === 'done' ? undefined : `inset 0 0 0 1.5px ${s.state === 'next' ? 'var(--color-accent)' : 'var(--color-fg-4)'}`,
                        }}>
                        {s.state === 'done' && <Check size={8} strokeWidth={3.5} className="text-[#0a0c0f]" />}
                      </span>
                      <div className="flex items-baseline gap-2">
                        <span className={`text-[13px] ${s.state === 'done' ? 'text-[var(--color-fg)]' : s.state === 'next' ? 'font-medium text-[var(--color-accent)]' : 'text-[var(--color-fg-2)]'}`}>{s.label}</span>
                        <span className="ml-auto text-[10.5px] text-[var(--color-fg-4)]">
                          {s.at ? <span className="num">{localTime(s.at)}</span> : s.state === 'next' ? 'next' : s.state === 'later' ? 'later' : 'skipped'}
                        </span>
                      </div>
                      <div className="mt-0.5 text-[11px] text-[var(--color-fg-4)]">seen as: {s.types.map(eventLabel).join(', ').toLowerCase()}</div>
                      <div className="mt-1 flex items-start gap-1.5 text-[11.5px] text-[var(--color-fg-3)]">
                        <ArrowRight size={11} className="mt-[3px] shrink-0" />
                        <span>intervention point: <span className="text-[var(--color-fg-2)]">{s.action_label}</span></span>
                      </div>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="text-[12.5px] leading-relaxed text-[var(--color-fg-3)]">These signals don't match a known crime script, so ARGUS doesn't project a next stage. The score can still change with more evidence (middle column).</p>
              )}
              <div className="mt-5 rounded-lg px-3 py-2.5 text-[11.5px] leading-relaxed text-[var(--color-fg-3)]" style={{ background: 'var(--color-surface-2)' }}>
                Stages follow <span className="text-[var(--color-fg-2)]">crime script analysis</span> (precursor → act → departure), so each one has its own
                intervention point. Scripts live in <span className="num">playbook.yaml</span>.
              </div>
            </div>
          </section>

          {/* 2 · what would change the score */}
          <section className="flex min-h-0 flex-col" style={{ borderRight: '1px solid var(--color-hair)' }}>
            <Head n={2} title="What would change the score" note={`bars: watch ${fc.thresholds.watch} · open ${fc.thresholds.open} · critical ${fc.thresholds.critical}`} />
            <div className="scroll min-h-0 flex-1 space-y-4 px-5 pb-5">
              {GROUPS.map((g) => {
                const rows = fc.whatifs.filter((w) => g.kind.includes(w.kind))
                if (!rows.length) return null
                return (
                  <div key={g.title}>
                    <div className="eyebrow mb-1.5">{g.title}</div>
                    <ul className="space-y-2.5">
                      {rows.map((w) => (
                        <li key={w.label}>
                          <div className="flex items-baseline gap-2">
                            <span className="text-[12.5px] text-[var(--color-fg)]">{w.label}</span>
                            <span className="num ml-auto text-[12px]" style={{ color: LEVEL_COLOR[w.level as Level] }}>{w.score}</span>
                            <span className="num w-9 text-right text-[11px]" style={{ color: w.delta > 0 ? 'var(--color-fg-2)' : 'var(--color-fg-4)' }}>
                              {w.delta > 0 ? `+${w.delta}` : w.delta}
                            </span>
                          </div>
                          <div className="mt-1"><ScoreBar value={w.score} base={fc.base.score} th={fc.thresholds} lvl={w.level} /></div>
                          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10.5px] text-[var(--color-fg-4)]">
                            <span>{w.detail}</span>
                            {w.title_changes && <span className="chip" style={{ height: 17, fontSize: 10 }}>becomes "{w.title}"</span>}
                            {w.opens && fc.base.level !== 'high' && fc.base.level !== 'critical' && <span className="chip" style={{ height: 17, fontSize: 10, color: 'var(--color-high)' }}>would open for a person</span>}
                            {w.basis && <span>· strength: {w.basis}</span>}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )
              })}
              <p className="text-[10.5px] leading-relaxed text-[var(--color-fg-4)]">
                Each bar is the real scorer run on this incident's evidence plus one hypothetical signal. The white tick is the score now.
              </p>
            </div>
          </section>

          {/* 3 · compare responses */}
          <section className="flex min-h-0 flex-col">
            <Head n={3} title="Compare responses" note="ranked: stops what's next, then fastest, then least disruptive" />
            <div className="scroll min-h-0 flex-1 px-5 pb-4">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[460px] text-left text-[12px]">
                  <thead>
                    <tr className="whitespace-nowrap text-[10.5px] uppercase tracking-[0.06em] text-[var(--color-fg-4)]">
                      <th className="pb-1.5 font-medium">Response</th>
                      <th className="pb-1.5 pr-2 font-medium">In effect</th>
                      <th className="pb-1.5 font-medium">Targets</th>
                      <th className="pb-1.5 pr-2 text-right font-medium" title="People affected">People</th>
                      <th className="pb-1.5 pr-2 text-right font-medium" title="How disruptive">Impact</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fc.responses.map((r) => {
                      const R = RESPONDER[r.responder]
                      const on = r.action === pick
                      return (
                        <tr key={r.action} onClick={() => setPick(r.action)} aria-selected={on}
                          className={`cursor-pointer align-top transition ${on ? 'bg-[var(--color-surface-3)]' : 'hover:bg-[var(--color-surface-2)]'}`}>
                          <td className="rounded-l-md py-2 pl-2 pr-2">
                            <div className="flex items-start gap-2">
                              <span className="num mt-px w-3 text-[10.5px] text-[var(--color-fg-4)]">{r.rank}</span>
                              <R.Icon size={13} strokeWidth={1.9} className="mt-0.5 shrink-0 text-[var(--color-fg-2)]" />
                              <span className="min-w-0">
                                <span className="block text-[var(--color-fg)]">{r.label}</span>
                                <span className="mt-0.5 flex flex-wrap gap-1">
                                  {r.rank === 1 && <span className="chip" style={{ height: 17, fontSize: 10, color: 'var(--color-accent)' }}>best fit now</span>}
                                  {r.recommended && <span className="chip" style={{ height: 17, fontSize: 10 }}>ARGUS recommends</span>}
                                </span>
                              </span>
                            </div>
                          </td>
                          <td className="num py-2 pr-2 text-[var(--color-fg-2)]">{r.time_to_effect_s === null ? '—' : r.time_to_effect_s === 0 ? 'now' : mmss(r.time_to_effect_s)}</td>
                          <td className="py-2 pr-2 text-[11.5px] text-[var(--color-fg-3)]">
                            {r.disrupts ? <span className={r.prevents_next ? 'text-[var(--color-accent)]' : ''}>{r.prevents_next ? 'stops: ' : 'later: '}{r.disrupts.toLowerCase()}</span>
                              : r.answers ? <>now: {r.answers.toLowerCase()}</> : 'general'}
                          </td>
                          <td className="num py-2 pr-2 text-right text-[var(--color-fg-2)]">{r.people_affected ?? '—'}</td>
                          <td className="rounded-r-md py-2 pr-2">
                            <span className="ml-auto flex w-fit gap-[3px]" title={['none', 'low', 'medium', 'high'][r.disruption]}>
                              {[1, 2, 3].map((d) => <span key={d} className="h-2 w-2 rounded-[2px]" style={{ background: r.disruption >= d ? 'var(--color-fg-2)' : 'var(--color-surface-4)' }} />)}
                            </span>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>

              {chosen && <Simulation r={chosen} fc={fc} left={left} />}
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-3 px-5 py-3 hairline-t">
              <p className="min-w-0 flex-1 text-[10.5px] leading-relaxed text-[var(--color-fg-4)]">
                Guard posts, walking speed and police / medical times are assumptions for this demo site (site.yaml <span className="num">response</span>).
              </p>
              {onApply && chosen && (
                done ? (
                  <span className="flex items-center gap-1.5 text-[12.5px] text-[var(--color-ok)]"><Check size={14} /> {done}</span>
                ) : (
                  <button className="btn btn-primary" disabled={busy || !!applyDisabled} title={applyDisabled ?? undefined}
                    onClick={async () => {
                      setBusy(true)
                      try { await onApply(chosen); setDone(`Recorded: ${chosen.records === 'ack' ? 'acknowledged' : 'escalated'}`) } finally { setBusy(false) }
                    }}>
                    {busy ? <LoaderCircle size={14} className="animate-spin" /> : <Check size={14} />}
                    Apply: {chosen.label.length > 34 ? chosen.label.slice(0, 32) + '…' : chosen.label}
                  </button>
                )
              )}
              {!onApply && <span className="text-[11.5px] text-[var(--color-fg-3)]">Simulation only: an uploaded clip has no one on the ground to send.</span>}
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}

function Head({ n, title, note }: { n: number; title: string; note: string }) {
  return (
    <div className="flex shrink-0 items-baseline gap-2 px-5 pb-3 pt-4">
      <span className="num text-[11px] text-[var(--color-fg-4)]">{n}</span>
      <span className="shrink-0 whitespace-nowrap text-[13.5px] font-medium text-[var(--color-fg)]">{title}</span>
      <span className="ml-auto min-w-0 truncate text-[10.5px] text-[var(--color-fg-4)]" title={note}>{note}</span>
    </div>
  )
}

/** One response played forward: when it takes effect against the evidence window, what it targets, what it costs. */
function Simulation({ r, fc, left }: { r: ResponseOption; fc: Forecast; left: number }) {
  const eta = r.time_to_effect_s
  const span = Math.max(60, (eta ?? 0), left) * 1.15
  const pct = (s: number) => `${Math.min(100, (s / span) * 100)}%`
  const camera = fc.responses.find((x) => x.responder === 'camera' && x.action !== r.action && (x.disrupts || x.answers))
  const R = RESPONDER[r.responder]
  const lines: string[] = []
  if (eta === 0) lines.push('Acts immediately.')
  else if (eta !== null) {
    lines.push(r.before_window_closes
      ? `In effect in ${mmss(eta)}, ${mmss(left - eta)} before the evidence window closes.`
      : `In effect in ${mmss(eta)}${left > 0 ? `, ${mmss(eta - left)} after the evidence window closes` : ''}.`)
    if (!r.before_window_closes && camera) lines.push(`Pair it with "${camera.label.toLowerCase()}", which acts at once.`)
  } else lines.push('No time estimate: the site layout is unknown here.')
  if (r.prevents_next && r.disrupts) lines.push(`Targets the next stage before it happens: ${r.disrupts.toLowerCase()}.`)
  else if (r.disrupts) lines.push(`Targets a later stage: ${r.disrupts.toLowerCase()}.`)
  else if (r.answers) lines.push(`Responds to what is happening now: ${r.answers.toLowerCase()}.`)
  if (r.people_basis && r.people_affected !== null) lines.push(`Touches about ${r.people_affected} ${r.people_affected === 1 ? 'person' : 'people'} (${r.people_basis}).`)
  lines.push(`Records the incident as ${r.records === 'ack' ? 'acknowledged' : 'escalated'} in the tamper-evident log.`)

  return (
    <div key={r.action} className="fade-in mt-4 rounded-xl p-3.5" style={{ background: 'var(--color-surface-2)', boxShadow: 'inset 0 0 0 1px var(--color-hair)' }}>
      <div className="eyebrow mb-3 flex items-center gap-1.5"><R.Icon size={12} strokeWidth={2} /> Simulate: {r.label}</div>
      <div className="relative mx-1 mb-6 mt-2 h-[3px] rounded-full bg-[var(--color-surface-4)]">
        {left > 0 && <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: pct(left), background: 'color-mix(in srgb, var(--color-accent) 45%, transparent)' }} />}
        {eta !== 0 && <Mark at="0%" label="now" />}
        {left > 0 && <Mark at={pct(left)} label={`window closes ${mmss(left)}`} muted />}
        {eta !== null && <Mark at={pct(eta)} label={eta === 0 ? 'in effect now' : `in effect ${mmss(eta)}`} strong />}
      </div>
      <ul className="space-y-1 text-[12px] leading-relaxed text-[var(--color-fg-2)]">
        {lines.map((l) => <li key={l} className="flex gap-2"><span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-[var(--color-fg-4)]" />{l}</li>)}
      </ul>
      <p className="mt-2 text-[10.5px] text-[var(--color-fg-4)]">{r.eta_basis} · {r.why}</p>
    </div>
  )
}

function Mark({ at, label, strong, muted }: { at: string; label: string; strong?: boolean; muted?: boolean }) {
  return (
    <span className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2" style={{ left: at }}>
      <span className="block h-3 w-3 rounded-full" style={{ background: strong ? 'var(--color-fg)' : muted ? 'var(--color-surface)' : 'var(--color-fg-3)', boxShadow: muted ? 'inset 0 0 0 1.5px var(--color-accent)' : undefined }} />
      <span className={`absolute top-4 whitespace-nowrap text-[10px] ${parseFloat(at) < 8 ? 'left-0' : parseFloat(at) > 88 ? 'right-0' : 'left-1/2 -translate-x-1/2'} ${strong ? 'text-[var(--color-fg)]' : 'text-[var(--color-fg-3)]'}`}>{label}</span>
    </span>
  )
}
