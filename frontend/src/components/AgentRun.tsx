import { Eye, FileSearch, ListChecks, LoaderCircle, Search, Smartphone, TrendingUp } from 'lucide-react'
import { useEffect, useState } from 'react'
import { API, eventLabel, localTime, modelName } from '../lib'
import type { ArgusEvent, Incident } from '../types'
import { SourceIcon } from './Symbols'

interface Step {
  n: number
  tool: string
  args: Record<string, unknown>
  summary: string
  ms: number
  image?: string
}

interface CaseFile {
  question: string
  as_of: string
  answer: string
  verdict: 'confirmed' | 'likely' | 'unclear' | 'false_alarm' | 'nothing_found'
  confidence: number
  next_step: string
  cited_incidents: string[]
  cited_events: ArgusEvent[]
  steps: Step[]
  generated_by: 'agent' | 'template'
  model: string | null
  seconds: number
  cached?: boolean
  error?: string
}

const TOOL: Record<string, { icon: typeof Eye; label: string }> = {
  list_incidents: { icon: ListChecks, label: 'Checked what ARGUS has raised' },
  get_incident: { icon: FileSearch, label: 'Pulled the evidence' },
  search_signals: { icon: Search, label: 'Searched the sensor log' },
  look_at_camera: { icon: Eye, label: 'Looked at the footage' },
  phones_in_area: { icon: Smartphone, label: 'Checked people’s phones' },
  forecast: { icon: TrendingUp, label: 'Forecast what happens next' },
}

const VERDICT: Record<CaseFile['verdict'], { label: string; color: string }> = {
  confirmed: { label: 'Confirmed', color: 'var(--color-crit)' },
  likely: { label: 'Likely real', color: 'var(--color-high)' },
  unclear: { label: 'Unclear', color: 'var(--color-watch)' },
  false_alarm: { label: 'Looks like a false alarm', color: 'var(--color-ok)' },
  nothing_found: { label: 'Nothing found', color: 'var(--color-ok)' },
}

interface Props {
  question: string
  incidents: Record<string, Incident>
  onSelect: (id: string) => void
  onJump: (e: ArgusEvent) => void
}

/**
 * The ARGUS investigator (backend/argus/agent.py), streamed: each tool call appears as the agent makes it (with the
 * frames it looked at), then the case file. The agent only recommends; the operator acts from the incident panel.
 */
export function AgentRun({ question, incidents, onSelect, onJump }: Props) {
  const [steps, setSteps] = useState<Step[]>([])
  const [result, setResult] = useState<CaseFile | null>(null)
  const [failed, setFailed] = useState(false)
  const [zoom, setZoom] = useState<string | null>(null)

  useEffect(() => {
    setSteps([]); setResult(null); setFailed(false)
    const src = new EventSource(`${API}/api/agent/stream?q=${encodeURIComponent(question)}`)
    src.addEventListener('step', (e) => setSteps((s) => [...s, JSON.parse((e as MessageEvent).data) as Step]))
    src.addEventListener('done', (e) => { setResult(JSON.parse((e as MessageEvent).data) as CaseFile); src.close() })
    src.onerror = () => { src.close(); setResult((r) => { if (!r) setFailed(true); return r }) }
    return () => src.close()
  }, [question])

  const v = result && !result.error ? VERDICT[result.verdict] ?? VERDICT.unclear : null
  return (
    <div className="fade-in">
      <div className="eyebrow mb-2">Investigation</div>
      <ol className="space-y-2">
        {steps.map((s) => {
          const t = TOOL[s.tool] ?? { icon: Search, label: s.tool }
          const Icon = t.icon
          return (
            <li key={s.n} className="fade-in flex gap-2.5">
              <span className="mt-[1px] flex h-[20px] w-[20px] shrink-0 items-center justify-center rounded-full"
                style={{ background: 'var(--color-surface-3)', boxShadow: 'inset 0 0 0 1px var(--color-hair-2)' }}>
                <Icon size={11} strokeWidth={2} className="text-[var(--color-accent)]" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-[11.5px] text-[var(--color-fg-3)]">
                  {t.label}
                  {typeof s.args.question === 'string' && <span className="text-[var(--color-fg-4)]"> · “{s.args.question}”</span>}
                </div>
                <div className="text-[12.5px] leading-snug text-[var(--color-fg)]">{s.summary}</div>
                {s.image && (
                  <button onClick={() => setZoom(zoom === s.image ? null : s.image!)} title="What the agent looked at (click to enlarge)"
                    className="mt-1.5 block overflow-hidden rounded-md" style={{ boxShadow: 'inset 0 0 0 1px var(--color-hair-2)' }}>
                    <img src={API + s.image} alt="Footage the agent checked" className="block w-full" loading="lazy" />
                  </button>
                )}
              </div>
            </li>
          )
        })}
        {!result && !failed && (
          <li className="flex items-center gap-2.5 text-[12px] text-[var(--color-fg-3)]">
            <LoaderCircle size={14} className="animate-spin text-[var(--color-accent)]" />
            {steps.length === 0 ? 'Planning the investigation…' : 'Working…'}
          </li>
        )}
      </ol>

      {zoom && (
        <button onClick={() => setZoom(null)} className="fixed inset-0 z-50 flex items-center justify-center p-6"
          style={{ background: 'rgb(0 0 0 / .8)' }} aria-label="Close">
          <img src={API + zoom} alt="Footage the agent checked" className="max-h-full max-w-full rounded-lg" />
        </button>
      )}

      {failed && <p className="mt-3 text-[12.5px] text-[var(--color-watch)]">The investigator could not run just now.</p>}
      {result?.error && <p className="mt-3 text-[12.5px] text-[var(--color-watch)]">{result.error}</p>}

      {result && v && (
        <div className="fade-in mt-3 rounded-lg p-3" style={{ background: 'var(--color-surface-3)', boxShadow: 'inset 0 0 0 1px var(--color-hair-2)' }}>
          <div className="mb-1.5 flex items-center gap-2">
            <span className="rounded px-1.5 py-0.5 text-[11px] font-medium"
              style={{ color: v.color, boxShadow: `inset 0 0 0 1px ${v.color}` }}>{v.label}</span>
            <span className="num text-[11px] text-[var(--color-fg-3)]">{Math.round(result.confidence * 100)}% sure</span>
            <span className="ml-auto text-[10.5px] text-[var(--color-fg-4)]">
              {result.generated_by === 'agent' ? `${modelName(result.model)} · ${result.steps.length} steps · ${result.seconds}s${result.cached ? ' · replayed' : ''}` : 'automatic summary'}
            </span>
          </div>
          <p className="text-[13px] leading-relaxed text-[var(--color-fg)]">{result.answer}</p>
          {result.next_step && (
            <p className="mt-2 text-[12.5px] leading-snug text-[var(--color-fg-2)]">
              <span className="eyebrow mr-1.5">Recommended</span>{result.next_step}
            </p>
          )}
          {(result.cited_incidents.length > 0 || result.cited_events.length > 0) && (
            <div className="mt-2.5 space-y-0.5">
              <div className="eyebrow mb-1">Evidence · click to open</div>
              {result.cited_incidents.map((id) => incidents[id] && (
                <button key={id} onClick={() => onSelect(id)}
                  className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-[12px] text-[var(--color-fg-2)] hover:bg-[var(--color-surface-4)] hover:text-[var(--color-fg)]">
                  <span className="num text-[var(--color-fg-3)]">{id}</span>
                  <span className="truncate">{incidents[id].title.split(' — ')[0]}</span>
                </button>
              ))}
              {result.cited_events.slice(0, 5).map((e) => (
                <button key={e.event_id} onClick={() => onJump(e)} title="Replay from 2 s before this"
                  className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-[12px] text-[var(--color-fg-3)] hover:bg-[var(--color-surface-4)] hover:text-[var(--color-fg)]">
                  <SourceIcon source={e.source} />
                  <span className="num">{localTime(e.t)}</span>
                  <span className="truncate">{eventLabel(e.type)} · <span className="num">{e.sensor_id}</span></span>
                </button>
              ))}
            </div>
          )}
          <p className="mt-2.5 text-[10.5px] leading-relaxed text-[var(--color-fg-4)]">
            The investigator only sees the past, checks footage itself and recommends; decisions stay with you.
          </p>
        </div>
      )}
    </div>
  )
}
