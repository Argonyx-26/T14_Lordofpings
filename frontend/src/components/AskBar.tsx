import { ArrowRight, CornerDownRight, LoaderCircle, MessageSquareText, X } from 'lucide-react'
import { useState } from 'react'
import { MOCK, localTime, post } from '../lib'
import type { ArgusEvent, Incident } from '../types'

interface Answer {
  question: string
  answer: string
  as_of: string
  cited_incidents: string[]
  cited_events: ArgusEvent[]
  generated_by: 'llm' | 'template'
  model: string | null
}

interface Props {
  incidents: Record<string, Incident>
  onSelect: (id: string) => void
  onJump: (e: ArgusEvent) => void
}

const SUGGESTIONS = ['What happened at the bus station?', 'Is anything going on at the school?', 'Summarise the last ten minutes']

/** Ask ARGUS (backend/argus/ask.py): answered only from what has been seen so far, with clickable citations. */
export function AskBar({ incidents, onSelect, onJump }: Props) {
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [answer, setAnswer] = useState<Answer | null>(null)
  const [error, setError] = useState<string | null>(null)

  const submit = async (question: string) => {
    if (!question.trim() || busy || MOCK) return
    setQ(question)
    setBusy(true)
    setError(null)
    try {
      setAnswer((await post('/api/ask', { question })) as Answer)
    } catch {
      setError('ARGUS could not answer just now.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="relative shrink-0">
      <form onSubmit={(ev) => { ev.preventDefault(); submit(q) }}
        className="surface flex items-center gap-2 px-3 py-2">
        <MessageSquareText size={14} strokeWidth={1.75} className="shrink-0 text-[var(--color-fg-3)]" />
        <input value={q} onChange={(ev) => setQ(ev.target.value)} disabled={MOCK}
          placeholder="Ask ARGUS about what has happened so far"
          className="min-w-0 flex-1 bg-transparent text-[12.5px] text-[var(--color-fg)] outline-none placeholder:text-[var(--color-fg-4)]" />
        <button type="submit" disabled={busy || !q.trim() || MOCK} aria-label="Ask"
          className="text-[var(--color-fg-3)] transition hover:text-[var(--color-fg)] disabled:opacity-40">
          {busy ? <LoaderCircle size={14} className="animate-spin" /> : <ArrowRight size={14} strokeWidth={1.75} />}
        </button>
      </form>

      {!answer && !busy && !q && !MOCK && (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {SUGGESTIONS.map((s) => (
            <button key={s} onClick={() => submit(s)}
              className="rounded-full px-2.5 py-0.5 text-[11px] text-[var(--color-fg-3)] transition hover:text-[var(--color-fg)]"
              style={{ boxShadow: 'inset 0 0 0 1px var(--color-hair-2)' }}>{s}</button>
          ))}
        </div>
      )}

      {(answer || error || busy) && (
        <div className="surface absolute inset-x-0 top-full z-30 mt-1.5 max-h-[340px] overflow-y-auto px-4 py-3 shadow-2xl"
          style={{ boxShadow: '0 12px 40px rgba(0,0,0,.55), inset 0 0 0 1px var(--color-hair-2)' }}>
          <div className="mb-1.5 flex items-center gap-2 text-[10.5px] text-[var(--color-fg-4)]">
            <span className="eyebrow">{busy ? 'Reading the log' : 'Answer'}</span>
            {answer && !busy && <span>as of <span className="num">{answer.as_of.slice(11, 16)}</span> · {answer.generated_by === 'llm' ? 'Gemini, from the log only' : 'automatic summary'}</span>}
            <button onClick={() => { setAnswer(null); setError(null); setQ('') }} aria-label="Close"
              className="ml-auto text-[var(--color-fg-4)] hover:text-[var(--color-fg)]"><X size={13} /></button>
          </div>
          {busy && <p className="text-[12.5px] text-[var(--color-fg-3)]">Checking incidents and signals up to now…</p>}
          {error && !busy && <p className="text-[12.5px] text-[var(--color-watch)]">{error}</p>}
          {answer && !busy && <>
            <p className="text-[13px] leading-relaxed text-[var(--color-fg)]">{answer.answer}</p>
            {(answer.cited_incidents.length > 0 || answer.cited_events.length > 0) && (
              <div className="mt-2.5 space-y-1">
                {answer.cited_incidents.map((id) => incidents[id] && (
                  <button key={id} onClick={() => onSelect(id)}
                    className="flex w-full items-center gap-2 text-left text-[11.5px] text-[var(--color-fg-2)] hover:text-[var(--color-fg)]">
                    <CornerDownRight size={12} className="shrink-0 text-[var(--color-fg-4)]" />
                    <span className="num text-[var(--color-fg-3)]">{id}</span>
                    <span className="truncate">{incidents[id].title.split(' — ')[0]}</span>
                  </button>
                ))}
                {answer.cited_events.slice(0, 6).map((e) => (
                  <button key={e.event_id} onClick={() => onJump(e)} title="Replay from 2 s before this"
                    className="flex w-full items-center gap-2 text-left text-[11.5px] text-[var(--color-fg-3)] hover:text-[var(--color-fg)]">
                    <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: `var(--color-${e.source})` }} />
                    <span className="num">{localTime(e.t)}</span>
                    <span className="truncate">{e.type.replaceAll('_', ' ')} · <span className="num">{e.sensor_id}</span></span>
                  </button>
                ))}
              </div>
            )}
          </>}
        </div>
      )}
    </div>
  )
}
