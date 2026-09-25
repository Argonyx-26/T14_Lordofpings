import { useEffect, useMemo, useState } from 'react'
import { CameraWall } from './components/CameraWall'
import { IncidentDetail } from './components/IncidentDetail'
import { IncidentQueue } from './components/IncidentQueue'
import { MetricsStrip } from './components/MetricsStrip'
import { SiteMap } from './components/SiteMap'
import { StreamPanel } from './components/StreamPanel'
import { TopBar, type Role } from './components/TopBar'
import { MOCK, post } from './lib'
import type { ArgusEvent, Incident } from './types'
import { useArgus } from './useArgus'

export default function App() {
  const { state, evidenceFor } = useArgus()
  const [selected, setSelected] = useState<string | null>(null)
  const [role, setRole] = useState<Role>('duty_officer')
  const [siloed, setSiloed] = useState(false)
  const incidents = useMemo(() => Object.values(state.incidents), [state.incidents])
  const live = selected ? state.incidents[selected] ?? null : null
  // Jumping back in time rebuilds the replay, so the selected incident briefly does not exist yet.
  // Keep showing its last known state (and evidence) until it re-forms with the same id.
  const [lastSeen, setLastSeen] = useState<Incident | null>(null)
  useEffect(() => { if (live) setLastSeen(live) }, [live])
  const current = live ?? (lastSeen && lastSeen.incident_id === selected ? lastSeen : null)
  const replayingLeadUp = !live && current !== null
  const [evidence, setEvidence] = useState<ArgusEvent[]>([])
  const [focus, setFocus] = useState<string | null>(null)
  const evidenceKey = live ? `${live.incident_id}:${live.event_ids.length}` : ''

  useEffect(() => {
    if (!live) { if (!current) setEvidence([]); return }
    evidenceFor(live.incident_id).then(setEvidence)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [evidenceKey])

  /** Evidence click: pause the replay 2 s before the event and enlarge the camera that saw it (or one in that area). */
  const jumpTo = (e: ArgusEvent) => {
    const cams = state.config?.cameras ?? {}
    const cam = cams[e.sensor_id] ? e.sensor_id
      : cams[e.sensor_id.split('-')[0]] ? e.sensor_id.split('-')[0]
      : Object.keys(cams).find((c) => cams[c].area === e.area) ?? null
    setFocus(cam)
    if (!MOCK) post('/api/replay', { cmd: 'pause' }).then(() => post('/api/replay', { cmd: 'seek', value: e.t - 2 })).catch(console.error)
  }

  return (
    <div className="flex h-full flex-col gap-2 p-2">
      <TopBar clock={state.clock} config={state.config} connected={state.connected} mock={state.mock} role={role} onRole={setRole} />
      <MetricsStrip summary={state.summary} />

      <main className="grid min-h-0 flex-1 grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_minmax(0,1.1fr)] gap-2">
        <div className="flex min-h-0 flex-col gap-2">
          <CameraWall config={state.config} clock={state.clock} incidents={incidents} evidence={evidence} focus={focus} onFocus={setFocus} />
          <section className="panel flex min-h-0 flex-1 flex-col">
            <div className="flex items-center justify-between border-b border-[var(--color-line)] px-3 py-2">
              <span className="label">{siloed ? 'Siloed view · per-stream alerts' : 'All streams · raw events'}</span>
              <button onClick={() => setSiloed(!siloed)} className="rounded bg-[var(--color-panel-2)] px-2 py-1 text-xs hover:bg-[var(--color-line)]">
                {siloed ? 'Show raw events' : 'Show siloed alerts'}
              </button>
            </div>
            <StreamPanel events={state.events} config={state.config} siloed={siloed} />
          </section>
        </div>

        <div className="flex min-h-0 flex-col gap-2">
          <IncidentQueue incidents={incidents} config={state.config} selected={selected} onSelect={setSelected} />
          <SiteMap config={state.config} incidents={incidents} />
        </div>

        <IncidentDetail incident={current} config={state.config} role={role} evidence={evidence} onJump={jumpTo} replayingLeadUp={replayingLeadUp} />
      </main>

      <footer className="px-1 text-[11px] text-[var(--color-dim)]">
        {state.config?.attribution} Door events are derived from human annotations; device locations are recorded GPS; CCTV analytics are computed by ARGUS.
      </footer>
    </div>
  )
}
