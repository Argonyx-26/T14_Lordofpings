import { useMemo, useState } from 'react'
import { CameraWall } from './components/CameraWall'
import { IncidentDetail } from './components/IncidentDetail'
import { IncidentQueue } from './components/IncidentQueue'
import { MetricsStrip } from './components/MetricsStrip'
import { SiteMap } from './components/SiteMap'
import { StreamPanel } from './components/StreamPanel'
import { TopBar, type Role } from './components/TopBar'
import { useArgus } from './useArgus'

export default function App() {
  const { state, evidenceFor } = useArgus()
  const [selected, setSelected] = useState<string | null>(null)
  const [role, setRole] = useState<Role>('duty_officer')
  const [siloed, setSiloed] = useState(false)
  const incidents = useMemo(() => Object.values(state.incidents), [state.incidents])
  const current = selected ? state.incidents[selected] ?? null : null

  return (
    <div className="flex h-full flex-col gap-2 p-2">
      <TopBar clock={state.clock} config={state.config} connected={state.connected} mock={state.mock} role={role} onRole={setRole} />
      <MetricsStrip summary={state.summary} />

      <main className="grid min-h-0 flex-1 grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_minmax(0,1.1fr)] gap-2">
        <div className="flex min-h-0 flex-col gap-2">
          <CameraWall config={state.config} clock={state.clock} incidents={incidents} />
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

        <IncidentDetail incident={current} config={state.config} role={role} evidenceFor={evidenceFor} />
      </main>

      <footer className="px-1 text-[11px] text-[var(--color-dim)]">
        {state.config?.attribution} Door events are derived from human annotations; device locations are recorded GPS; CCTV analytics are computed by ARGUS.
      </footer>
    </div>
  )
}
