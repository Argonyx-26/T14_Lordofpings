import { ArrowRight, CornerDownRight, LoaderCircle, Sparkles, X } from 'lucide-react'
import { AgentRun } from './AgentRun'
import { useEffect, useRef, useState } from 'react'
import { MOCK, eventLabel, localTime, modelName, post, track } from '../lib'
import type { ArgusEvent, Incident } from '../types'
import { SourceIcon } from './Symbols'

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
const INVESTIGATE = ['Investigate the most serious open incident', 'Is the unattended bag at the bus station real?', 'Did anything get stolen at the school?']

/**
 * Ask ARGUS (backend/argus/ask.py): answered only from what has been seen so far, with clickable citations.
 * Lives behind a search-style trigger in the header ("/" opens it) so it costs no space until it is wanted.
 */
export function AskBar({ incidents, onSelect, onJump }: Props) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [answer, setAnswer] = useState<Answer | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<'ask' | 'investigate'>('ask')
  const [case_, setCase] = useState<string | null>(null)       // the question the investigator is working on
  const input = useRef<HTMLInputElement>(null)
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && e.target.closest('input, textarea, [contenteditable]')
      if (e.key === '/' && !typing) { e.preventDefault(); setOpen(true) }
      if (e.key === 'Escape') setOpen(false)
    }
    const click = (e: MouseEvent) => { if (root.current && !root.current.contains(e.target as Node)) setOpen(false) }
    window.addEventListener('keydown', key)
    window.addEventListener('mousedown', click)
    return () => { window.removeEventListener('keydown', key); window.removeEventListener('mousedown', click) }
  }, [])
  useEffect(() => { if (open) input.current?.focus() }, [open])

  const submit = async (question: string) => {
    track('ask_argus', { mode, offline_demo: MOCK })
    if (!question.trim() || busy || MOCK) return
    setQ(question)
    if (mode === 'investigate') { setAnswer(null); setError(null); setCase(question); return }
    setCase(null)
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
    <div ref={root} className="relative">
      <button onClick={() => setOpen(!open)} disabled={MOCK} aria-expanded={open}
        title={MOCK ? 'Needs the backend' : 'Ask a question in plain words, answered only from what ARGUS has seen'}
        className="flex h-[30px] w-full items-center gap-2 rounded-[7px] px-2.5 text-left text-[12.5px] text-[var(--color-fg-3)] transition hover:text-[var(--color-fg-2)] disabled:opacity-50"
        style={{ background: 'var(--color-surface-2)', boxShadow: 'inset 0 0 0 1px var(--color-hair-2)' }}>
        <Sparkles size={13} strokeWidth={1.75} className="shrink-0 text-[var(--color-accent)]" />
        <span className="hidden truncate lg:inline">Ask ARGUS what has happened</span>
        <span className="truncate lg:hidden">Ask</span>
        <span className="kbd ml-auto hidden lg:inline">/</span>
      </button>

      {open && (
        <div className={`pop absolute left-0 top-full z-40 mt-2 rounded-xl ${mode === 'investigate' ? 'w-[min(560px,calc(100vw-24px))]' : 'w-[min(460px,calc(100vw-24px))]'}`}
          style={{ background: 'var(--color-surface-2)', boxShadow: '0 18px 50px rgb(0 0 0 / .6), inset 0 0 0 1px var(--color-hair-2)' }}>
          <div className="flex gap-1 px-3.5 pt-3" role="tablist">
            {(['ask', 'investigate'] as const).map((m) => (
              <button key={m} role="tab" aria-selected={mode === m} onClick={() => { setMode(m); setCase(null); setAnswer(null); setError(null); input.current?.focus() }}
                title={m === 'ask' ? 'A quick answer from the log' : 'An agent works the case: pulls evidence, checks the footage itself, checks phones, then gives a verdict'}
                className={`rounded-md px-2 py-1 text-[11.5px] transition ${mode === m ? 'bg-[var(--color-surface-4)] text-[var(--color-fg)]' : 'text-[var(--color-fg-3)] hover:text-[var(--color-fg)]'}`}>
                {m === 'ask' ? 'Ask' : 'Investigate · agent'}
              </button>
            ))}
          </div>
          <form onSubmit={(ev) => { ev.preventDefault(); submit(q) }} className="flex items-center gap-2 px-3.5 py-3 hairline-b">
            <Sparkles size={14} strokeWidth={1.75} className="shrink-0 text-[var(--color-accent)]" />
            <input ref={input} value={q} onChange={(ev) => setQ(ev.target.value)}
              placeholder={mode === 'ask' ? 'Ask about anything ARGUS has seen so far' : 'What should the investigator look into?'}
              className="min-w-0 flex-1 bg-transparent text-[13px] text-[var(--color-fg)] outline-none placeholder:text-[var(--color-fg-4)]" />
            <button type="submit" disabled={busy || !q.trim()} aria-label="Ask"
              className="btn btn-icon btn-sm border-transparent">
              {busy ? <LoaderCircle size={14} className="animate-spin" /> : <ArrowRight size={14} strokeWidth={1.75} />}
            </button>
          </form>

          <div className={`scroll px-3.5 py-3 ${mode === 'investigate' ? 'max-h-[min(640px,calc(100vh-120px))]' : 'max-h-[380px]'}`}>
            {case_ && <AgentRun question={case_} incidents={incidents} onSelect={(id) => { onSelect(id); setOpen(false) }}
              onJump={(e) => { onJump(e); setOpen(false) }} />}
            {!case_ && !answer && !busy && !error && (
              <>
                <div className="eyebrow mb-2">Try</div>
                <div className="flex flex-col items-start gap-1">
                  {(mode === 'ask' ? SUGGESTIONS : INVESTIGATE).map((s) => (
                    <button key={s} onClick={() => submit(s)}
                      className="flex items-center gap-2 rounded-md px-1.5 py-1 text-[12.5px] text-[var(--color-fg-2)] transition hover:bg-[var(--color-surface-3)] hover:text-[var(--color-fg)]">
                      <CornerDownRight size={12} className="text-[var(--color-fg-4)]" /> {s}
                    </button>
                  ))}
                </div>
                <p className="mt-3 text-[11px] leading-relaxed text-[var(--color-fg-4)]">
                  {mode === 'ask'
                    ? 'Answers come only from the incidents and signals logged up to the replay clock, and cite them.'
                    : 'An agent plans the case and uses ARGUS’s tools: incidents, the sensor log, the camera footage itself (with a vision model) and people’s phones. It only sees the past and only recommends.'}
                </p>
              </>
            )}
            {busy && <p className="text-[12.5px] text-[var(--color-fg-3)]">Reading incidents and signals up to now…</p>}
            {error && !busy && <p className="text-[12.5px] text-[var(--color-watch)]">{error}</p>}
            {answer && !busy && (
              <div className="fade-in">
                <div className="mb-1.5 flex items-center gap-2 text-[10.5px] text-[var(--color-fg-4)]">
                  <span className="eyebrow">Answer</span>
                  <span>as of <span className="num">{answer.as_of.slice(11, 16)}</span> · {answer.generated_by === 'llm' ? `${modelName(answer.model)}, from the log only` : 'automatic summary'}</span>
                  <button onClick={() => { setAnswer(null); setError(null); setQ(''); input.current?.focus() }} aria-label="Clear"
                    className="ml-auto text-[var(--color-fg-4)] hover:text-[var(--color-fg)]"><X size={13} /></button>
                </div>
                <p className="text-[13px] leading-relaxed text-[var(--color-fg)]">{answer.answer}</p>
                {(answer.cited_incidents.length > 0 || answer.cited_events.length > 0) && (
                  <div className="mt-3 space-y-0.5">
                    <div className="eyebrow mb-1">Sources · click to open</div>
                    {answer.cited_incidents.map((id) => incidents[id] && (
                      <button key={id} onClick={() => { onSelect(id); setOpen(false) }}
                        className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-[12px] text-[var(--color-fg-2)] hover:bg-[var(--color-surface-3)] hover:text-[var(--color-fg)]">
                        <span className="num text-[var(--color-fg-3)]">{id}</span>
                        <span className="truncate">{incidents[id].title.split(' — ')[0]}</span>
                      </button>
                    ))}
                    {answer.cited_events.slice(0, 6).map((e) => (
                      <button key={e.event_id} onClick={() => { onJump(e); setOpen(false) }} title="Replay from 2 s before this"
                        className="flex w-full items-center gap-2 rounded-md px-1.5 py-1 text-left text-[12px] text-[var(--color-fg-3)] hover:bg-[var(--color-surface-3)] hover:text-[var(--color-fg)]">
                        <SourceIcon source={e.source} />
                        <span className="num">{localTime(e.t)}</span>
                        <span className="truncate">{eventLabel(e.type)} · <span className="num">{e.sensor_id}</span></span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
