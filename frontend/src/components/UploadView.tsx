import { ChevronRight, FileVideo, LoaderCircle, TriangleAlert, Upload } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { API, LEVEL_COLOR, eventLabel, scoreColor, severityLabel } from '../lib'
import { CLASS_STYLE } from '../tracks'
import { Still, hasStill } from './Still'
import type { ArgusEvent, Forecast, Incident, SiteConfigView } from '../types'
import { ResponsePlanner } from './Forecast'
import { StatusSymbol } from './Symbols'

interface Job {
  id: string
  name: string
  created: number
  status: 'queued' | 'tracking' | 'rules' | 'done' | 'error'
  progress: number
  message: string
  meta: { fps?: number; width?: number; height?: number; duration_s?: number; start_t?: number; stem?: string }
  result?: {
    events: ArgusEvent[]
    incidents: Incident[]
    evidence: Record<string, ArgusEvent[]>
    summary: { raw_events: number; signals: number }
  } | null
}

type Det = { frame: number; cls: number; conf: number; xyxy: [number, number, number, number]; tid?: number }

const CANVAS_W = 1920 // upload tracks are normalised to the vision rules' 1920x1072 canvas
const CANVAS_H = 1072
const FPS = 30
const WEAPON_CONF = 0.5 // the weapon rule's own threshold (vision/threats.py WEAPON_CONF)
const SIGNAL_HOLD_S = 1.5 // how long a signal's frozen box stays after the moment it fired

const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`

/** Analyse any video: upload it, then review detections, events and incidents on the footage itself. */
export function UploadView({ config }: { config: SiteConfigView | null }) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [selected, setSelected] = useState<string | null>(new URLSearchParams(location.search).get('upload'))
  const [job, setJob] = useState<Job | null>(null)
  const [sending, setSending] = useState<{ name: string; pct: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [thorough, setThorough] = useState(true)

  const refreshList = useCallback(() => {
    fetch(`${API}/api/uploads`).then((r) => r.json()).then(setJobs).catch(() => {})
  }, [])
  useEffect(refreshList, [refreshList])

  // Poll the selected job until it finishes.
  useEffect(() => {
    if (!selected) { setJob(null); return }
    let stop = false
    let timer: ReturnType<typeof setTimeout>
    const poll = () =>
      fetch(`${API}/api/uploads/${selected}`).then((r) => r.json()).then((j: Job) => {
        if (stop) return
        setJob(j)
        if (j.status !== 'done' && j.status !== 'error') timer = setTimeout(poll, 1000)
        else refreshList()
      }).catch(() => { if (!stop) timer = setTimeout(poll, 2000) })
    poll()
    return () => { stop = true; clearTimeout(timer) }
  }, [selected, refreshList])

  const send = (file: File) => {
    setError(null)
    const form = new FormData()
    form.append('file', file)
    form.append('thorough', String(thorough))
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API}/api/uploads`)
    xhr.upload.onprogress = (e) => e.lengthComputable && setSending({ name: file.name, pct: e.loaded / e.total })
    xhr.onload = () => {
      setSending(null)
      if (xhr.status >= 200 && xhr.status < 300) {
        const j = JSON.parse(xhr.responseText) as Job
        refreshList()
        setSelected(j.id)
      } else {
        try { setError(JSON.parse(xhr.responseText).detail) } catch { setError(`Upload failed (${xhr.status})`) }
      }
    }
    xhr.onerror = () => { setSending(null); setError('Upload failed: is the backend running?') }
    setSending({ name: file.name, pct: 0 })
    xhr.send(form)
  }

  return (
    <div className="grid min-h-0 flex-1 grid-cols-[300px_minmax(0,1fr)] gap-3 p-3">
      <aside className="flex min-h-0 flex-col gap-3">
        <Dropzone onFile={send} busy={!!sending} />
        <label className="flex cursor-pointer items-start gap-2.5 px-1 text-[12px] leading-snug text-[var(--color-fg-2)]">
          <input type="checkbox" checked={thorough} onChange={(e) => setThorough(e.target.checked)} className="mt-0.5 accent-[var(--color-fg)]" />
          <span>
            <span className="text-[var(--color-fg)]">Thorough scan</span>: also looks closely for small bags, phones and
            laptops. Untick for a quick scan, about twice as fast.
          </span>
        </label>
        {sending && (
          <div className="surface px-4 py-3 text-[12px]">
            <div className="truncate text-[var(--color-fg)]">Uploading {sending.name}</div>
            <Bar value={sending.pct} />
          </div>
        )}
        {error && <div className="surface px-4 py-3 text-[12px] text-[var(--color-crit)]">{error}</div>}
        <section className="surface flex min-h-0 flex-1 flex-col">
          <div className="flex h-10 shrink-0 items-center px-4 hairline-b">
            <span className="text-[13px] font-medium">Analyses</span>
            <span className="num ml-2 text-[11px] text-[var(--color-fg-3)]">{jobs.length}</span>
          </div>
          <div className="scroll min-h-0 flex-1">
            {jobs.length === 0 && <p className="p-4 text-[12px] text-[var(--color-fg-4)]">Nothing analysed yet.</p>}
            {jobs.map((j) => (
              <button key={j.id} onClick={() => setSelected(j.id)}
                className={`flex w-full items-start gap-3 px-4 py-2.5 text-left transition hairline-b ${selected === j.id ? 'bg-[var(--color-surface-2)]' : 'hover:bg-[var(--color-surface-2)]/60'}`}>
                <FileVideo size={15} strokeWidth={1.5} className="mt-0.5 shrink-0 text-[var(--color-fg-3)]" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[12.5px] text-[var(--color-fg)]">{j.name}</span>
                  <span className={`block truncate text-[11px] ${j.status === 'error' ? 'text-[var(--color-crit)]' : 'text-[var(--color-fg-3)]'}`}>
                    {j.status === 'done' ? j.message : j.status === 'error' ? 'Failed' : 'Analysing…'}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </section>
      </aside>

      <main className="min-h-0 min-w-0">
        {!job && <Intro />}
        {job && job.status !== 'done' && <Progress job={job} />}
        {job && job.status === 'done' && job.result && <Review job={job} config={config} />}
      </main>
    </div>
  )
}

function Dropzone({ onFile, busy }: { onFile: (f: File) => void; busy: boolean }) {
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  return (
    <div
      onClick={() => !busy && input.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setOver(true) }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); const f = e.dataTransfer.files[0]; if (f && !busy) onFile(f) }}
      className={`flex cursor-pointer flex-col items-center gap-2 rounded-lg border border-dashed px-4 py-7 text-center transition ${over ? 'border-[var(--color-fg-2)] bg-[var(--color-surface-2)]' : 'border-[var(--color-hair-2)] hover:border-[var(--color-fg-3)]'}`}>
      <Upload size={18} strokeWidth={1.5} className="text-[var(--color-fg-2)]" />
      <span className="text-[13px] text-[var(--color-fg)]">Drop a video, or click to choose</span>
      <span className="text-[11px] text-[var(--color-fg-4)]">MP4, AVI, MOV, MKV or WebM · up to 2 GB</span>
      <input ref={input} type="file" accept="video/*,.avi,.mkv" hidden
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = '' }} />
    </div>
  )
}

function Intro() {
  const steps = [
    ['Track', 'People, vehicles, bags, laptops and phones are detected and followed frame by frame (YOLO11 + ByteTrack).'],
    ['Detect', 'The same rules as the live console flag unattended bags, bags taken, running, crowding, and (with their models) weapons, fights, falls and hand-offs.'],
    ['Assess', 'Fusion turns those signals into scored, explained incidents under the security profile you pick: airport, school or park.'],
    ['Project', 'Each incident gets a forecast: the stage it has reached, what would raise or lower its risk, and responses compared side by side.'],
  ]
  return (
    <section className="surface flex h-full flex-col items-center justify-center gap-4 px-10 text-center">
      <span className="display text-[34px] text-[var(--color-fg)]">Assess any security footage</span>
      <p className="max-w-xl text-[13px] leading-relaxed text-[var(--color-fg-2)]">
        Drop in a clip from any camera, even a phone. ARGUS runs its full pipeline on it and returns a threat assessment you can replay moment by moment.
      </p>
      <ol className="mt-2 grid max-w-3xl grid-cols-1 gap-3 text-left sm:grid-cols-2">
        {steps.map(([t, body], k) => (
          <li key={t} className="rounded-lg px-4 py-3" style={{ background: 'var(--color-surface-2)' }}>
            <div className="text-[13px] font-medium text-[var(--color-fg)]"><span className="num text-[var(--color-fg-4)]">{k + 1}</span> {t}</div>
            <div className="mt-1 text-[12px] leading-relaxed text-[var(--color-fg-3)]">{body}</div>
          </li>
        ))}
      </ol>
      <p className="max-w-xl text-[11.5px] leading-relaxed text-[var(--color-fg-4)]">
        Door and walkway rules need a camera's zones drawn once, so they only run on the site's own cameras.
      </p>
    </section>
  )
}

function Progress({ job }: { job: Job }) {
  const failed = job.status === 'error'
  return (
    <section className="surface flex h-full flex-col items-center justify-center gap-4 px-10 text-center">
      {failed
        ? <TriangleAlert size={22} strokeWidth={1.5} className="text-[var(--color-crit)]" />
        : <LoaderCircle size={22} strokeWidth={1.5} className="animate-spin text-[var(--color-fg-2)]" />}
      <span className="display text-[30px] text-[var(--color-fg)]">{failed ? 'Analysis failed' : job.name}</span>
      <span className={`text-[13px] ${failed ? 'text-[var(--color-crit)]' : 'text-[var(--color-fg-2)]'}`}>{job.message}</span>
      {!failed && (
        <div className="w-80">
          <Bar value={job.status === 'queued' ? 0 : job.progress} />
          <div className="num mt-1.5 text-[11px] text-[var(--color-fg-3)]">
            {Math.round((job.status === 'queued' ? 0 : job.progress) * 100)}%
            {job.meta.duration_s ? ` · ${mmss(job.meta.duration_s)} of footage` : ''}
          </div>
        </div>
      )}
    </section>
  )
}

function Bar({ value }: { value: number }) {
  return (
    <div className="mt-2 h-[3px] w-full rounded-full bg-[var(--color-surface-3)]">
      <div className="h-full rounded-full bg-[var(--color-fg-2)] transition-all" style={{ width: `${Math.max(2, value * 100)}%` }} />
    </div>
  )
}

function Review({ job, config }: { job: Job; config: SiteConfigView | null }) {
  const video = useRef<HTMLVideoElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const [tracks, setTracks] = useState<Map<number, Det[]> | null>(null)
  const [weapons, setWeapons] = useState<Map<number, Det[]> | null>(null)
  const [time, setTime] = useState(0)
  const [boxes, setBoxes] = useState(true)
  const result = job.result!
  const start = job.meta.start_t ?? 0
  const duration = job.meta.duration_s || 1
  // stable across renders: the overlay's draw loop restarts whenever this changes
  const signals = useMemo(() => result.events.filter((e) => e.type !== 'occupancy'), [result])
  const cfg = config ?? undefined
  const [profile, setProfile] = useState<string | null>(config?.profile ?? null)
  const [assessment, setAssessment] = useState<Assessment | null>(null)
  const [plan, setPlan] = useState<string | null>(null)

  // The threat assessment under the chosen profile (re-fused on the server from the clip's stored signals).
  useEffect(() => {
    let stale = false
    fetch(`${API}/api/uploads/${job.id}/assess${profile ? `?profile=${profile}` : ''}`)
      .then((r) => (r.ok ? r.json() : null)).then((a) => { if (!stale) setAssessment(a) }).catch(() => {})
    return () => { stale = true }
  }, [job.id, profile])

  useEffect(() => {
    const load = (what: string, minConf: number) =>
      fetch(`${API}/api/uploads/${job.id}/${what}`).then((r) => (r.ok ? r.text() : '')).then((text) => {
        const index = new Map<number, Det[]>()
        for (const line of text.split('\n')) {
          if (!line) continue
          const d = JSON.parse(line) as Det
          if (d.conf < minConf) continue
          const list = index.get(d.frame)
          if (list) list.push(d)
          else index.set(d.frame, [d])
        }
        return index
      })
    load('tracks', 0).then(setTracks)
    load('weapons', WEAPON_CONF).then(setWeapons)
  }, [job.id])

  // Overlay: boxes live on a 1920x1072 canvas scaled per axis onto the displayed video.
  useEffect(() => {
    let raf = 0
    const draw = () => {
      raf = requestAnimationFrame(draw)
      const v = video.current
      const c = canvas.current
      if (!v || !c || !v.videoWidth) return
      const W = c.clientWidth
      const H = c.clientHeight
      if (c.width !== W || c.height !== H) { c.width = W; c.height = H }
      const ctx = c.getContext('2d')!
      ctx.clearRect(0, 0, W, H)
      const s = Math.min(W / v.videoWidth, H / v.videoHeight)
      const dw = v.videoWidth * s
      const dh = v.videoHeight * s
      const ox = (W - dw) / 2
      const oy = (H - dh) / 2
      const rect = (b: number[]) => [ox + (b[0] / CANVAS_W) * dw, oy + (b[1] / CANVAS_H) * dh, ((b[2] - b[0]) / CANVAS_W) * dw, ((b[3] - b[1]) / CANVAS_H) * dh] as const
      const frame = Math.round(v.currentTime * FPS)
      // the detections nearest this frame (analysed frames are 2-3 clock frames apart), never older than ~0.13 s
      const near = (index: Map<number, Det[]>) => {
        for (let k = 0; k <= 4; k++) {
          const d = index.get(frame - k) ?? index.get(frame + k)
          if (d?.length) return d
        }
        return []
      }
      // the weapon detector's own boxes, frame by frame: they follow the weapon and go when it goes
      const armed = boxes && weapons ? near(weapons) : []
      for (const d of armed) {
        const [x, y, w, h] = rect(d.xyxy)
        ctx.lineWidth = 2.5
        ctx.strokeStyle = '#ef4f4f'
        ctx.strokeRect(x, y, w, h)
        ctx.fillStyle = '#ef4f4f'
        ctx.font = 'bold 12px ui-sans-serif, system-ui'
        ctx.fillText(`weapon ${Math.round(d.conf * 100)}%`, x, y - 4)
      }
      if (boxes && tracks) {
        const dets = near(tracks)
        ctx.lineWidth = 1.5
        ctx.font = '11px ui-monospace, monospace'
        for (const d of dets) {
          const st = CLASS_STYLE[d.cls] ?? { label: String(d.cls), color: '#aaa' }
          const [x, y, w, h] = rect(d.xyxy)
          ctx.strokeStyle = st.color
          ctx.strokeRect(x, y, w, h)
          ctx.fillStyle = st.color
          ctx.fillText(`${st.label}${d.tid !== undefined ? ' #' + d.tid : ''}`, x + 2, y - 3)
        }
      }
      // A signal's box is where it was confirmed, frozen: show it from just before that moment for a short while,
      // not +-2 s. A weapon alert whose weapon is boxed live right now needs no frozen copy.
      for (const e of signals) {
        if (!e.media?.bbox) continue
        const dt = frame - e.media.frame
        if (dt < -0.3 * FPS || dt > SIGNAL_HOLD_S * FPS) continue
        if (e.type === 'weapon_visible' && armed.length) continue
        const [x, y, w, h] = rect(e.media.bbox)
        if (w <= 0 || h <= 0) continue
        const strong = e.severity >= 0.5 // hand-offs (0.3) and the like are context, not alarms
        const color = strong ? '#ef4f4f' : '#f0b429'
        ctx.lineWidth = strong ? 3 : 1.5
        ctx.strokeStyle = color
        ctx.strokeRect(x - 3, y - 3, w + 6, h + 6)
        ctx.fillStyle = color
        ctx.font = `${strong ? 'bold 13px' : '11px'} ui-sans-serif, system-ui`
        ctx.fillText(e.type.replaceAll('_', ' '), x - 3, y - 9)
      }
    }
    raf = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(raf)
  }, [tracks, weapons, boxes, signals])

  const seek = (t: number) => {
    const v = video.current
    if (!v) return
    v.currentTime = Math.max(0, t - start - 2)
    v.play().catch(() => {})
  }

  const incidents = assessment?.incidents ?? result.incidents
  const evidence = assessment?.evidence ?? result.evidence
  const planning = plan ? incidents.find((i) => i.incident_id === plan) ?? null : null

  return (
    <div className="grid h-full min-h-0 grid-cols-[minmax(0,1fr)_360px] gap-3">
      <section className="flex min-h-0 flex-col gap-3">
        <Verdict a={assessment} profiles={config?.profiles ?? []} profile={profile} onProfile={setProfile} name={job.name}
          meta={`${job.meta.width}×${job.meta.height} · ${job.meta.fps} fps · ${mmss(duration)}`} />
        <div className="relative min-h-0 flex-1 overflow-hidden rounded-md bg-black" style={{ boxShadow: 'inset 0 0 0 1px var(--color-hair)' }}>
          <video ref={video} src={`${API}/api/uploads/${job.id}/video`} controls playsInline muted
            onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)} className="absolute inset-0 h-full w-full object-contain" />
          <canvas ref={canvas} className="pointer-events-none absolute inset-0 h-full w-full" />
          <button className="btn btn-sm absolute right-2 top-2 bg-black/60" onClick={() => setBoxes(!boxes)}>{boxes ? 'Hide detections' : 'Show detections'}</button>
        </div>
        <RiskChart a={assessment} signals={signals} start={start} duration={duration} time={time} onSeek={seek} />
      </section>

      <aside className="flex min-h-0 flex-col gap-3">
        <section className="surface shrink-0 px-4 py-3">
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Detections" value={tracks ? [...tracks.values()].reduce((n, d) => n + d.length, 0).toLocaleString() : '…'} />
            <Stat label="Signals" value={String(signals.length)} />
            <Stat label="Incidents" value={String(incidents.length)} />
          </div>
        </section>
        <section className="surface flex min-h-0 flex-1 flex-col">
          <div className="flex h-10 shrink-0 items-center px-4 hairline-b">
            <span className="text-[13px] font-medium">Flagged</span>
            <span className="ml-auto text-[11px] text-[var(--color-fg-3)]">{assessment ? assessment.profile_label : ''}</span>
          </div>
          <div className="scroll min-h-0 flex-1">
            {incidents.length === 0 && (
              <p className="px-4 py-4 text-[12px] leading-relaxed text-[var(--color-fg-3)]">
                Nothing in this clip rose to an incident under this profile. The signals below are what the detectors noticed.
              </p>
            )}
            {incidents.map((i) => {
              const color = scoreColor(i.score, cfg)
              const fc = assessment?.forecasts[i.incident_id]
              const next = fc?.whatifs.find((w) => w.kind === 'next_stage')
              return (
                <div key={i.incident_id} className="relative px-4 py-3 hairline-b">
                  <span className="absolute inset-y-0 left-0 w-[3px]" style={{ background: color }} />
                  <button onClick={() => seek(i.first_signal_at)} className="flex w-full items-start gap-3 text-left">
                    <span className="figure w-8 shrink-0 text-[20px]" style={{ color }}>{i.score}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-[13px] leading-snug text-[var(--color-fg)]">{i.title.split(' — ')[0]}</span>
                      <span className="mt-0.5 block text-[11px] text-[var(--color-fg-3)]">
                        <span className="num">{mmss(i.first_signal_at - start)}</span> in the clip · <span style={{ color }}>{i.status === 'watch' ? 'Watch' : severityLabel(i.score, cfg)}</span>
                      </span>
                      {i.brief && <span className="mt-1 block text-[11.5px] leading-snug text-[var(--color-fg-2)]">{i.brief.summary}</span>}
                    </span>
                  </button>
                  {(() => {
                    const key = (evidence[i.incident_id] ?? []).filter(hasStill)
                      .reduce<ArgusEvent | null>((a, e) => (!a || e.severity > a.severity ? e : a), null)
                    return key && <Still key={key.event_id} e={key} job={job.id} className="mt-2 aspect-video w-full" />
                  })()}
                  {fc && (
                    <div className="mt-2.5 rounded-md px-2.5 py-2 text-[11.5px] leading-relaxed text-[var(--color-fg-2)]" style={{ background: 'var(--color-surface-2)' }}>
                      {next ? <>{next.label}: <span className="num">{i.score}</span> → <span className="num" style={{ color: scoreColor(next.score, cfg) }}>{next.score}</span>{next.title_changes ? <>, "{next.title}"</> : null}.</>
                        : 'No known escalation path from these signals.'}
                      {fc.responses[0] && <span className="block text-[var(--color-fg-3)]">Best response now: {fc.responses[0].label.toLowerCase()}.</span>}
                      <button className="mt-1.5 flex items-center gap-1 text-[12px] font-medium text-[var(--color-fg)] hover:underline" onClick={() => setPlan(i.incident_id)}>
                        Plan the response <ChevronRight size={13} />
                      </button>
                    </div>
                  )}
                </div>
              )
            })}
            <div className="eyebrow px-4 pb-1 pt-4">Signals</div>
            {signals.length === 0 && <p className="px-4 pb-4 text-[12px] text-[var(--color-fg-4)]">No signals beyond routine head counts.</p>}
            {signals.map((e) => (
              <button key={e.event_id} onClick={() => seek(e.t)}
                className="grid w-full grid-cols-[44px_1fr_auto] items-center gap-2 px-4 py-1.5 text-left text-[12px] hover:bg-[var(--color-surface-2)]">
                <span className="num text-[var(--color-fg-3)]">{mmss(e.t - start)}</span>
                <span className="truncate text-[var(--color-fg)]">{eventLabel(e.type)}</span>
                <span>{hasStill(e) && <Still key={e.event_id} e={e} job={job.id} className="h-[32px] w-[57px]" />}</span>
              </button>
            ))}
          </div>
        </section>
      </aside>
      {planning && assessment?.forecasts[planning.incident_id] && (
        <ResponsePlanner fc={assessment.forecasts[planning.incident_id]} incident={planning} clock={null}
          areaName={`${job.name} (uploaded)`} onClose={() => setPlan(null)} />
      )}
    </div>
  )
}

interface Assessment {
  profile: string | null
  profile_label: string
  thresholds: { watch: number; open: number }
  verdict: { level: 'critical' | 'high' | 'watch' | 'low' | 'clear'; headline: string; incidents: number; signals: number; kinds: Record<string, number> }
  timeline: { t: number; score: number; incident_id: string; type: string }[]
  incidents: Incident[]
  evidence: Record<string, ArgusEvent[]>
  forecasts: Record<string, Forecast>
}

/** The clip's verdict in one line, the kinds of signal found, and the security profile it was judged under. */
function Verdict({ a, profiles, profile, onProfile, name, meta }: {
  a: Assessment | null; profiles: { id: string; label: string; description: string }[]; profile: string | null
  onProfile: (p: string) => void; name: string; meta: string
}) {
  const lvl = a?.verdict.level ?? 'clear'
  const color = LEVEL_COLOR[lvl]
  return (
    <div className="relative shrink-0 overflow-hidden rounded-lg px-4 py-3" style={{
      background: `linear-gradient(90deg, color-mix(in srgb, ${color} 12%, var(--color-surface)), var(--color-surface) 70%)`,
      boxShadow: 'inset 0 0 0 1px var(--color-hair)',
    }}>
      <span className="absolute inset-y-0 left-0 w-[3px]" style={{ background: color }} />
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <StatusSymbol level={lvl} size={10} />
            <span className="eyebrow" style={{ color }}>Threat assessment{a ? '' : ' · loading'}</span>
            <span className="truncate text-[11px] text-[var(--color-fg-4)]">{name} · {meta}</span>
          </div>
          <div className="mt-1 text-[17px] font-semibold tracking-[-0.01em] text-[var(--color-fg)]">{a?.verdict.headline ?? 'Assessing…'}</div>
          {a && Object.keys(a.verdict.kinds).length > 0 && (
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {Object.entries(a.verdict.kinds).slice(0, 6).map(([k, n]) => <span key={k} className="chip">{k} <span className="num text-[var(--color-fg-3)]">{n}</span></span>)}
            </div>
          )}
        </div>
        {profiles.length > 0 && (
          <div className="seg" aria-label="Judge this clip as">
            {profiles.map((p) => <button key={p.id} data-on={p.id === profile} onClick={() => onProfile(p.id)} title={p.description}>{p.label}</button>)}
          </div>
        )}
      </div>
    </div>
  )
}

/** Risk over the clip: the highest live incident score after each signal, on the profile's watch / open lines. */
function RiskChart({ a, signals, start, duration, time, onSeek }: {
  a: Assessment | null; signals: ArgusEvent[]; start: number; duration: number; time: number; onSeek: (t: number) => void
}) {
  const W = 1000
  const H = 70
  const x = (t: number) => ((t - start) / duration) * W
  const y = (s: number) => H - 6 - (Math.min(100, s) / 100) * (H - 12)
  const pts = a?.timeline ?? []
  let d = `M0 ${y(0)}`
  let prev = 0
  for (const p of pts) { d += ` L${x(p.t)} ${y(prev)} L${x(p.t)} ${y(p.score)}`; prev = p.score }
  d += ` L${W} ${y(prev)}`
  return (
    <div className="shrink-0 rounded-md px-3 pb-1.5 pt-2" style={{ background: 'var(--color-surface)', boxShadow: 'inset 0 0 0 1px var(--color-hair)' }}>
      <div className="mb-1 flex items-center gap-3 text-[10.5px] text-[var(--color-fg-3)]">
        <span className="eyebrow">Risk over the clip</span>
        {a && <span>watch {a.thresholds.watch} · opens for a person at {a.thresholds.open}</span>}
        <span className="ml-auto">click to jump</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-[70px] w-full cursor-pointer"
        onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); onSeek(start + ((e.clientX - r.left) / r.width) * duration + 2) }}>
        {a && [a.thresholds.watch, a.thresholds.open].map((t) => (
          <line key={t} x1="0" x2={W} y1={y(t)} y2={y(t)} stroke="var(--color-hair-2)" strokeDasharray="4 4" vectorEffect="non-scaling-stroke" />
        ))}
        <path d={`${d} L${W} ${H} L0 ${H} Z`} fill="color-mix(in srgb, var(--color-high) 14%, transparent)" />
        <path d={d} fill="none" stroke="var(--color-high)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
        {signals.map((e) => (
          <line key={e.event_id} x1={x(e.t)} x2={x(e.t)} y1={H - 5} y2={H} stroke={e.severity >= 0.25 ? 'var(--color-fg-2)' : 'var(--color-fg-4)'} strokeWidth="2" vectorEffect="non-scaling-stroke" />
        ))}
        <line x1={(time / duration) * W} x2={(time / duration) * W} y1="0" y2={H} stroke="var(--color-fg)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
      </svg>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="eyebrow">{label}</div>
      <div className="display mt-1 text-[26px] text-[var(--color-fg)]">{value}</div>
    </div>
  )
}
