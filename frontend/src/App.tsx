import { useEffect, useMemo, useState } from 'react'
import { CameraWall } from './components/CameraWall'
import { IncidentDetail } from './components/IncidentDetail'
import { IncidentQueue } from './components/IncidentQueue'
import { MetricsStrip } from './components/MetricsStrip'
import { SiteMap } from './components/SiteMap'
import { StreamPanel } from './components/StreamPanel'
import { TopBar, type Role } from './components/TopBar'
import { UploadView } from './components/UploadView'
import { MOCK, post } from './lib'
import type { ArgusEvent, Incident } from './types'
import { useArgus } from './useArgus'

export default function App() {
  const { state, evidenceFor } = useArgus()
  const [selected, setSelected] = useState<string | null>(null)
  const [role, setRole] = useState<Role>('duty_officer')
  const [siloed, setSiloed] = useState(false)
  const [view, setView] = useState<'console' | 'upload'>('console')
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
    <div className="flex h-full min-w-[1280px] flex-col">
      <TopBar clock={state.clock} config={state.config} connected={state.connected} mock={state.mock} role={role} onRole={setRole}
        onAnalyse={() => setView(view === 'upload' ? 'console' : 'upload')} analysing={view === 'upload'} />
      {view === 'upload' ? <UploadView config={state.config} onBack={() => setView('console')} /> : <>
      <MetricsStrip summary={state.summary} />

      <main className="grid min-h-0 flex-1 grid-cols-[minmax(0,1.55fr)_minmax(0,0.9fr)_minmax(0,1.05fr)] gap-3 p-3">
        <div className="flex min-h-0 flex-col gap-3">
          <CameraWall config={state.config} clock={state.clock} incidents={incidents} evidence={evidence} focus={focus} onFocus={setFocus} />
          <StreamPanel events={state.events} config={state.config} siloed={siloed} onSiloed={setSiloed} />
        </div>

        <div className="flex min-h-0 flex-col gap-3">
          <IncidentQueue incidents={incidents} config={state.config} selected={selected} onSelect={setSelected} />
          <SiteMap config={state.config} incidents={incidents} />
        </div>

        <IncidentDetail incident={current} config={state.config} role={role} evidence={evidence} onJump={jumpTo} replayingLeadUp={replayingLeadUp} />
      </main>
      </>}

      <footer className="flex shrink-0 items-center gap-4 px-5 py-2 text-[10.5px] text-[var(--color-fg-4)] hairline-t">
        <span>{state.config?.attribution}</span>
        <span className="ml-auto">CCTV analytics computed by Argus · door events derived from annotations · device locations recorded GPS</span>
      </footer>
    </div>
  )
}
