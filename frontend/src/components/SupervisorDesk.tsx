import { Download, GraduationCap, Link2, RotateCcw, ScrollText, ShieldCheck, Undo2, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { MOCK, STATUS_LABEL, eventLabel, get, localTime, post } from '../lib'
import type { Incident, LearnedRule, SiteConfigView } from '../types'
import { StatusSymbol } from './Symbols'

type Tab = 'log' | 'learned' | 'dismissed'
interface Entry { incident_id: string; action: string; role: string; note: string; sim_t: number; score: number; hash: string; prev_hash: string }
interface Dismissed extends Incident { dismissed_by: Entry | null }

const ACTION: Record<string, string> = {
  ack: 'Acknowledged', escalate: 'Escalated', dismiss: 'Dismissed', reopen: 'Reopened', profile: 'Site profile changed',
  reset_learning: 'Lesson reset',
}

/**
 * Oversight that only a supervisor has (the backend refuses anyone else): the whole decision log with its chain check
 * and an export, what ARGUS has learned from dismissals (and resetting a lesson), and the incidents the floor
 * dismissed (and reopening one).
 */
export function SupervisorDesk({ config, onClose, onOpen }: { config: SiteConfigView | null; onClose: () => void; onOpen: (id: string) => void }) {
  const [tab, setTab] = useState<Tab>('log')
  const [log, setLog] = useState<{ verified: boolean; entries: Entry[] } | null>(null)
  const [rules, setRules] = useState<LearnedRule[] | null>(null)
  const [gone, setGone] = useState<Dismissed[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (MOCK) return
    try {
      const [a, l, d] = await Promise.all([get('/api/audit'), get('/api/learning'), get('/api/dismissed')])
      if (!a.ok) throw new Error(a.status === 401 ? 'Supervisor PIN needed' : `The backend refused (${a.status})`)
      setLog(await a.json()); setRules((await l.json()).rules); setGone((await d.json()).incidents)
      setError(null)
    } catch (e) { setError(String((e as Error).message ?? e)) }
  }, [])
  useEffect(() => { load() }, [load])
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onClose])

  const run = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key)
    try { await fn(); await load() } catch (e) { setError(String((e as Error).message ?? e)) } finally { setBusy(null) }
  }
  const exportLog = async () => {
    const r = await get('/api/audit/export')
    if (!r.ok) { setError(`Export refused (${r.status})`); return }
    const url = URL.createObjectURL(new Blob([await r.text()], { type: 'application/x-ndjson' }))
    const a = Object.assign(document.createElement('a'), { href: url, download: 'argus-decision-log.jsonl' })
    a.click()
    URL.revokeObjectURL(url)
  }
  const area = (a: string) => config?.areas[a]?.name ?? a

  const tabs: { id: Tab; label: string; n: number | null; Icon: typeof ScrollText }[] = [
    { id: 'log', label: 'Decision log', n: log?.entries.length ?? null, Icon: ScrollText },
    { id: 'learned', label: 'What ARGUS learned', n: rules?.length ?? null, Icon: GraduationCap },
    { id: 'dismissed', label: 'Dismissed', n: gone?.length ?? null, Icon: Undo2 },
  ]

  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-center bg-black/60 p-2 backdrop-blur-[2px] sm:p-5" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-label="Supervisor desk"
        className="pop flex max-h-full w-full max-w-[900px] flex-col overflow-hidden rounded-2xl"
        style={{ background: 'var(--color-surface)', boxShadow: '0 30px 80px rgb(0 0 0 / .6), inset 0 0 0 1px var(--color-hair-2)' }}>
        <div className="flex shrink-0 items-center gap-3 px-5 py-3.5 hairline-b">
          <ShieldCheck size={15} strokeWidth={1.75} className="text-[var(--color-accent)]" />
          <div className="min-w-0">
            <div className="eyebrow">Supervisor desk · oversight and policy</div>
            <div className="text-[15px] font-semibold tracking-[-0.01em]">What the floor decided, and what ARGUS learned from it</div>
          </div>
          <button onClick={onClose} className="btn btn-ghost btn-icon ml-auto" aria-label="Close supervisor desk"><X size={16} /></button>
        </div>

        <div className="flex shrink-0 gap-1 px-5 pt-3" role="tablist">
          {tabs.map((t) => (
            <button key={t.id} role="tab" aria-selected={tab === t.id} data-on={tab === t.id} onClick={() => setTab(t.id)} className="btn btn-sm">
              <t.Icon size={13} strokeWidth={1.75} /> {t.label}{t.n !== null && <span className="num text-[var(--color-fg-3)]">{t.n}</span>}
            </button>
          ))}
        </div>

        <div className="scroll min-h-0 flex-1 px-5 py-4 text-[12.5px] leading-relaxed text-[var(--color-fg-2)]">
          {MOCK && <p className="text-[var(--color-fg-3)]">The supervisor desk reads the live decision log and the engine's state: it needs the backend (run the demo laptop).</p>}
          {error && <p className="mb-3 rounded-lg px-3 py-2 text-[var(--color-crit)]" style={{ background: 'color-mix(in srgb, var(--color-crit) 10%, transparent)' }}>{error}</p>}

          {tab === 'log' && log && (
            <>
              <div className="mb-3 flex items-center gap-2">
                <span className="flex items-center gap-1.5 text-[12px]" style={{ color: log.verified ? 'var(--color-ok)' : 'var(--color-crit)' }}>
                  {log.verified ? <ShieldCheck size={13} /> : <Link2 size={13} />}
                  {log.verified ? `Hash chain intact over all ${log.entries.length} entries` : 'Hash chain broken: an entry was edited'}
                </span>
                <button className="btn btn-sm ml-auto" onClick={exportLog}><Download size={13} /> Export (JSON Lines)</button>
              </div>
              {log.entries.length === 0 ? <p className="text-[var(--color-fg-3)]">No decisions yet.</p> : (
                <ol className="space-y-1">
                  {[...log.entries].reverse().map((e) => (
                    <li key={e.hash} className="grid grid-cols-[64px_minmax(0,1fr)_auto] items-baseline gap-3">
                      <span className="num text-[var(--color-fg-3)]">{localTime(e.sim_t)}</span>
                      <span className="min-w-0 truncate">
                        <span className="text-[var(--color-fg)]">{ACTION[e.action] ?? e.action}</span>
                        {e.incident_id !== '-' && <button className="num ml-1.5 text-[var(--color-accent)] hover:underline" onClick={() => { onOpen(e.incident_id); onClose() }}>{e.incident_id}</button>}
                        <span className="text-[var(--color-fg-3)]"> · {e.role === 'supervisor' ? 'Supervisor' : 'Duty officer'}{e.note ? ` · ${config?.playbook[e.note] ?? (e.note === 'false_alarm' ? 'marked as a false alarm' : e.note)}` : ''}</span>
                      </span>
                      <span className="num text-[10.5px] text-[var(--color-fg-4)]" title={`hash ${e.hash}\nprev ${e.prev_hash}`}>{e.hash.slice(0, 10)}</span>
                    </li>
                  ))}
                </ol>
              )}
            </>
          )}

          {tab === 'learned' && rules && (
            <>
              <p className="mb-3 text-[12px] text-[var(--color-fg-3)]">
                Every dismissal teaches ARGUS to score the same signal lower in the same area (×{rules[0]?.penalty ?? 0.7} each). This is the whole of what it has learned; a lesson that
                was wrong can be reset, and live incidents there are re-scored at once.
              </p>
              {rules.length === 0 ? <p className="text-[var(--color-fg-3)]">Nothing learned yet: no dismissals.</p> : (
                <ul className="space-y-2">
                  {rules.map((r) => (
                    <li key={r.area + r.type} className="flex items-center gap-3 rounded-lg px-3 py-2" style={{ boxShadow: 'inset 0 0 0 1px var(--color-hair)' }}>
                      <span className="min-w-0 flex-1">
                        <span className="text-[var(--color-fg)]">{eventLabel(r.type)}</span> <span className="text-[var(--color-fg-3)]">in {r.area_name}</span>
                        <span className="block text-[11px] text-[var(--color-fg-3)]">
                          scores ×<span className="num">{r.factor}</span> · taught by {r.dismissals.length ? r.dismissals.map((d) => `${d.incident_id} (${localTime(d.sim_t)})`).join(', ') : 'earlier dismissals'}
                        </span>
                      </span>
                      <button className="btn btn-sm" disabled={busy !== null} onClick={() => run(r.area + r.type, () => post('/api/learning/reset', { area: r.area, type: r.type }))}>
                        <RotateCcw size={12} /> {busy === r.area + r.type ? 'Resetting…' : 'Reset'}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}

          {tab === 'dismissed' && gone && (
            <>
              <p className="mb-3 text-[12px] text-[var(--color-fg-3)]">What the floor chose to ignore. Reopening puts the incident back in front of a person and takes back the lesson its dismissal taught.</p>
              {gone.length === 0 ? <p className="text-[var(--color-fg-3)]">No dismissed incidents.</p> : (
                <ul className="space-y-2">
                  {gone.map((i) => (
                    <li key={i.incident_id} className="flex items-center gap-3 rounded-lg px-3 py-2" style={{ boxShadow: 'inset 0 0 0 1px var(--color-hair)' }}>
                      <StatusSymbol level="low" size={9} />
                      <span className="min-w-0 flex-1">
                        <span className="text-[var(--color-fg)]">{i.title.split(' — ')[0]}</span> <span className="num text-[var(--color-fg-3)]">{i.incident_id}</span>
                        <span className="block text-[11px] text-[var(--color-fg-3)]">
                          {area(i.area)} · peak <span className="num">{i.peak_score}</span> · {STATUS_LABEL[i.status]}
                          {i.dismissed_by && <> by {i.dismissed_by.role === 'supervisor' ? 'the supervisor' : 'the duty officer'} at <span className="num">{localTime(i.dismissed_by.sim_t)}</span></>}
                        </span>
                      </span>
                      <button className="btn btn-sm" disabled={busy !== null}
                        onClick={() => run(i.incident_id, async () => { await post(`/api/incidents/${i.incident_id}/action`, { action: 'reopen', role: 'supervisor', note: 'reopened' }); onOpen(i.incident_id) })}>
                        <Undo2 size={12} /> {busy === i.incident_id ? 'Reopening…' : 'Reopen'}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
