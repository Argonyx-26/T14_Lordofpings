import { useEffect, useMemo, useState } from 'react'
import { LazyMotion, MotionConfig } from 'motion/react'
import { AskBar } from './components/AskBar'
import { ArgusEye, type EyeCamera } from './components/ArgusEye'
import { Boot } from './components/Boot'
import { CameraWall } from './components/CameraWall'
import { IncidentDetail } from './components/IncidentDetail'
import { IncidentQueue } from './components/IncidentQueue'
import { ReplayBar } from './components/ReplayBar'
import { SiteMap } from './components/SiteMap'
import { SituationBand } from './components/SituationBand'
import { StreamPanel } from './components/StreamPanel'
import { TopBar, type Role } from './components/TopBar'
import { SupervisorDesk } from './components/SupervisorDesk'
import { UploadView } from './components/UploadView'
import { MOCK, WALL, camerasFor, clipAt, isActive, levelOf, pickPrimary, post, rankIncidents, shouldBoot, situation } from './lib'
import type { ArgusEvent, Incident } from './types'
import { useArgus, useIntel } from './useArgus'

const loadMotion = () => import('./motionFeatures').then((m) => m.default)

export default function App() {
  const { state, evidenceFor, forecastFor } = useArgus()
  const intel = useIntel(state)
  // ?incident=INC-0007 preselects an incident (handy for screenshots and links)
  const [selected, setSelected] = useState<string | null>(new URLSearchParams(location.search).get('incident'))
  const [role, setRole] = useState<Role>('duty_officer')
  const [desk, setDesk] = useState(false)
  const [siloed, setSiloed] = useState(false)
  const [streamOpen, setStreamOpen] = useState(false)
  // ?upload=<job id> opens that analysed clip
  const [view, setView] = useState<'console' | 'upload'>(new URLSearchParams(location.search).has('upload') ? 'upload' : 'console')
  const incidents = useMemo(() => Object.values(state.incidents), [state.incidents])

  // Nothing picked: show the most urgent incident that still sits in front of a person.
  const urgent = useMemo(() => rankIncidents(incidents).find((i) => isActive(i.status)) ?? null, [incidents])
  const live = selected ? state.incidents[selected] ?? null : urgent
  // Jumping back in time rebuilds the replay, so the selected incident briefly does not exist yet.
  // Keep showing its last known state (and evidence) until it re-forms with the same id.
  const [lastSeen, setLastSeen] = useState<Incident | null>(null)
  useEffect(() => { if (live && selected) setLastSeen(live) }, [live, selected])
  const current = live ?? (lastSeen && lastSeen.incident_id === selected ? lastSeen : null)
  const replayingLeadUp = !live && current !== null
  const [evidence, setEvidence] = useState<ArgusEvent[]>([])
  const [focus, setFocus] = useState<string | null>(null)
  const evidenceKey = live ? `${live.incident_id}:${live.event_ids.length}:${role}` : ''   // the role decides how much of it the backend sends

  useEffect(() => {
    if (!live) { if (!current) setEvidence([]); return }
    let stale = false
    evidenceFor(live.incident_id).then((e) => { if (!stale) setEvidence(e) })
    return () => { stale = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [evidenceKey])

  const select = (id: string) => { setSelected(id); setFocus(null) }

  /** Evidence click: pause the replay 2 s before the event and put the camera that saw it (or one in that area) on the main screen. */
  const jumpTo = (e: ArgusEvent) => {
    const cams = state.config?.cameras ?? {}
    const cam = cams[e.sensor_id] ? e.sensor_id
      : cams[e.sensor_id.split('-')[0]] ? e.sensor_id.split('-')[0]
      : Object.keys(cams).find((c) => cams[c].area === e.area) ?? null
    setFocus(cam)
    if (!MOCK) post('/api/replay', { cmd: 'pause' }).then(() => post('/api/replay', { cmd: 'seek', value: e.t - 2 })).catch(console.error)
  }

  // which camera is on the main screen (the map highlights it)
  const cfg = state.config
  const wall = cfg ? WALL.filter((c) => cfg.cameras[c]) : []
  const primary = cfg ? pickPrimary(wall, focus, camerasFor(current, evidence, cfg, wall),
    (c) => !!state.clock && !!clipAt(cfg, c, state.clock.sim_t)).camera : null

  // what the eye shows per camera: footage now, and the level of any live incident in its area
  const eyeCameras: EyeCamera[] = useMemo(() => wall.map((id) => {
    const area = cfg?.cameras[id]?.area
    const hot = incidents.filter((i) => isActive(i.status) && i.area === area).sort((a, b) => b.score - a.score)[0]
    return { id, footage: !!cfg && !!state.clock && !!clipAt(cfg, id, state.clock.sim_t), level: hot ? levelOf(hot.score, cfg ?? undefined) : null }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [cfg, incidents, state.clock ? Math.floor(state.clock.sim_t / 5) : 0])

  // boot sequence (once per session): the eye opens full screen, then hands over to the top band
  const [boot, setBoot] = useState(shouldBoot)
  const [eyeHome, setEyeHome] = useState(() => !boot)

  return (
    <LazyMotion features={loadMotion} strict>
    <MotionConfig reducedMotion="user">
    {boot && (
      <Boot ready={!!state.config} linked={!!state.clock} clock={state.clock} events={state.events} cameras={eyeCameras}
        onLeave={() => setEyeHome(true)}
        onDone={() => { setBoot(false); try { sessionStorage.setItem('argus-booted', '1') } catch { /* private mode */ } }} />
    )}
    {desk && role === 'supervisor' && <SupervisorDesk config={state.config} onClose={() => setDesk(false)} onOpen={select} />}
    <div className="app">
      <TopBar config={state.config} summary={state.summary} connected={state.connected} mock={state.mock} role={role} onRole={setRole}
        onAnalyse={() => setView(view === 'upload' ? 'console' : 'upload')} analysing={view === 'upload'} onDesk={() => setDesk(true)}
        ask={<AskBar incidents={state.incidents} onSelect={select} onJump={jumpTo} />} />
      {view === 'upload' ? <UploadView config={state.config} /> : <>
        <ReplayBar clock={state.clock} config={state.config} incidents={incidents} mock={state.mock} onSelect={select} />
        <SituationBand summary={state.summary} incidents={incidents} config={state.config} clock={state.clock} onSelect={select}
          events={state.events} cameras={eyeCameras} eye={eyeHome} />

        <main className="console">
          <div className="area-feed">
            <CameraWall config={state.config} clock={state.clock} incidents={incidents} current={current} evidence={evidence}
              focus={focus} onFocus={setFocus} />
            <StreamPanel events={state.events} total={state.summary?.raw_events ?? 0} config={state.config}
              siloed={siloed} onSiloed={setSiloed} open={streamOpen} onOpen={setStreamOpen} />
          </div>

          <div className="area-rail">
            <IncidentQueue incidents={incidents} config={state.config} clock={state.clock} selected={current?.incident_id ?? null} onSelect={select} intel={intel} />
            <SiteMap config={state.config} incidents={incidents} primary={primary} onFocus={setFocus} intel={intel} selected={current?.incident_id ?? null} />
          </div>

          <div className="area-detail">
            <IncidentDetail incident={current} auto={!selected && !!current} config={state.config} clock={state.clock} summary={state.summary}
              role={role} evidence={evidence} onJump={jumpTo} replayingLeadUp={replayingLeadUp}
              forecastFor={forecastFor} profile={state.config?.profile} intel={intel} incidents={state.incidents} onSelect={select}
              eye={<ArgusEye size={188} level={situation(incidents, state.config ?? undefined).level} score={null} events={state.events} clock={state.clock} cameras={eyeCameras}
                contextMax={state.config?.thresholds.context_max_severity} />} />
          </div>
        </main>
      </>}

      <footer className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 px-4 py-1.5 text-[10.5px] text-[var(--color-fg-4)] hairline-t">
        <span>{state.config?.attribution}</span>
        <span className="ml-auto">Camera analytics computed by Argus · door events derived from annotations · phone locations are recorded GPS</span>
      </footer>
    </div>
    </MotionConfig>
    </LazyMotion>
  )
}
