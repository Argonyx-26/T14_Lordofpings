import { ArrowLeft, FileVideo, LoaderCircle, TriangleAlert, Upload } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { API, scoreColor, severityLabel } from '../lib'
import { CLASS_STYLE } from '../tracks'
import type { ArgusEvent, Incident, SiteConfigView } from '../types'

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

const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`

/** Analyse any video: upload it, then review detections, events and incidents on the footage itself. */
export function UploadView({ config, onBack }: { config: SiteConfigView | null; onBack: () => void }) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [sending, setSending] = useState<{ name: string; pct: number } | null>(null)
  const [error, setError] = useState<string | null>(null)

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
        <button className="btn self-start" onClick={onBack}><ArrowLeft size={14} strokeWidth={1.75} /> Back to the console</button>
        <Dropzone onFile={send} busy={!!sending} />
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
  return (
    <section className="surface flex h-full flex-col items-center justify-center gap-3 px-10 text-center">
      <span className="display text-[40px] text-[var(--color-fg)]">Analyse any footage</span>
      <p className="max-w-xl text-[13px] leading-relaxed text-[var(--color-fg-2)]">
        Upload a clip and Argus runs the same detector, tracker, rules and fusion as the live console on it: people,
        vehicles, bags, laptops and phones are tracked, then unattended objects, objects changing hands or taken,
        running and crowding become scored, explained incidents.
      </p>
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
  const [time, setTime] = useState(0)
  const [boxes, setBoxes] = useState(true)
  const result = job.result!
  const start = job.meta.start_t ?? 0
  const duration = job.meta.duration_s || 1
  const signals = result.events.filter((e) => e.type !== 'occupancy')
  const cfg = config ?? undefined

  useEffect(() => {
    fetch(`${API}/api/uploads/${job.id}/tracks`).then((r) => (r.ok ? r.text() : '')).then((text) => {
      const index = new Map<number, Det[]>()
      for (const line of text.split('\n')) {
        if (!line) continue
        const d = JSON.parse(line) as Det
        const list = index.get(d.frame)
        if (list) list.push(d)
        else index.set(d.frame, [d])
      }
      setTracks(index)
    })
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
      if (boxes && tracks) {
        let dets: Det[] = []
        for (let k = 0; k <= 4 && !dets.length; k++) dets = tracks.get(frame - k) ?? tracks.get(frame + k) ?? []
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
      for (const e of signals) {
        if (!e.media?.bbox || Math.abs(e.media.frame - frame) > 2 * FPS) continue
        const [x, y, w, h] = rect(e.media.bbox)
        if (w <= 0 || h <= 0) continue
        ctx.lineWidth = 3
        ctx.strokeStyle = '#ef4f4f'
        ctx.strokeRect(x - 3, y - 3, w + 6, h + 6)
        ctx.fillStyle = '#ef4f4f'
        ctx.font = 'bold 13px ui-sans-serif, system-ui'
        ctx.fillText(e.type.replaceAll('_', ' '), x - 3, y - 9)
      }
    }
    raf = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(raf)
  }, [tracks, boxes, signals])

  const seek = (t: number) => {
    const v = video.current
    if (!v) return
    v.currentTime = Math.max(0, t - start - 2)
    v.play().catch(() => {})
  }

  return (
    <div className="grid h-full min-h-0 grid-cols-[minmax(0,1fr)_340px] gap-3">
      <section className="flex min-h-0 flex-col gap-3">
        <div className="flex h-7 items-center gap-3">
          <span className="truncate text-[13px] font-medium">{job.name}</span>
          <span className="num text-[11px] text-[var(--color-fg-3)]">
            {job.meta.width}×{job.meta.height} · {job.meta.fps} fps · {mmss(duration)}
          </span>
          <button className="btn ml-auto" onClick={() => setBoxes(!boxes)}>{boxes ? 'Hide detections' : 'Show detections'}</button>
        </div>
        <div className="relative min-h-0 flex-1 overflow-hidden rounded-md bg-black" style={{ boxShadow: 'inset 0 0 0 1px var(--color-hair)' }}>
          <video ref={video} src={`${API}/api/uploads/${job.id}/video`} controls playsInline muted
            onTimeUpdate={(e) => setTime(e.currentTarget.currentTime)} className="absolute inset-0 h-full w-full object-contain" />
          <canvas ref={canvas} className="pointer-events-none absolute inset-0 h-full w-full" />
        </div>
        {/* Event timeline: every signal at its moment in the clip; click to jump there */}
        <div className="relative h-9 shrink-0 rounded-md bg-[var(--color-surface)]" style={{ boxShadow: 'inset 0 0 0 1px var(--color-hair)' }}>
          <div className="absolute inset-y-0 w-px bg-[var(--color-fg)]" style={{ left: `${(time / duration) * 100}%` }} />
          {signals.map((e) => (
            <button key={e.event_id} title={`${mmss(e.t - start)} · ${e.type.replaceAll('_', ' ')}`} onClick={() => seek(e.t)}
              className="absolute top-1/2 h-4 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-sm"
              style={{ left: `${((e.t - start) / duration) * 100}%`, background: e.severity >= 0.25 ? 'var(--color-high)' : 'var(--color-fg-3)' }} />
          ))}
        </div>
      </section>

      <aside className="flex min-h-0 flex-col gap-3">
        <section className="surface shrink-0 px-4 py-3">
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Detections" value={tracks ? [...tracks.values()].reduce((n, d) => n + d.length, 0).toLocaleString() : '…'} />
            <Stat label="Events" value={String(signals.length)} />
            <Stat label="Incidents" value={String(result.incidents.length)} />
          </div>
        </section>
        <section className="surface flex min-h-0 flex-1 flex-col">
          <div className="flex h-10 shrink-0 items-center px-4 hairline-b">
            <span className="text-[13px] font-medium">Incidents</span>
          </div>
          <div className="scroll min-h-0 flex-1">
            {result.incidents.length === 0 && (
              <p className="px-4 py-4 text-[12px] leading-relaxed text-[var(--color-fg-3)]">
                Nothing in this clip rose to an incident. The events below are what the detectors noticed.
              </p>
            )}
            {result.incidents.map((i) => {
              const color = scoreColor(i.score, cfg)
              return (
                <button key={i.incident_id} onClick={() => seek(i.first_signal_at)}
                  className="relative flex w-full items-start gap-3 px-4 py-3 text-left transition hairline-b hover:bg-[var(--color-surface-2)]">
                  <span className="absolute inset-y-0 left-0 w-[2px]" style={{ background: color }} />
                  <span className="num w-8 shrink-0 text-[20px] font-medium leading-none" style={{ color }}>{i.score}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[13px] text-[var(--color-fg)]">{i.title.split(' — ')[0]}</span>
                    <span className="mt-0.5 block text-[11px] text-[var(--color-fg-3)]">
                      <span className="num">{mmss(i.first_signal_at - start)}</span> · <span style={{ color }}>{i.status === 'watch' ? 'Watch' : severityLabel(i.score, cfg)}</span>
                    </span>
                    {i.brief && <span className="mt-1 block text-[11.5px] leading-snug text-[var(--color-fg-2)]">{i.brief.summary}</span>}
                  </span>
                </button>
              )
            })}
            <div className="eyebrow px-4 pb-1 pt-4">Events</div>
            {signals.length === 0 && <p className="px-4 pb-4 text-[12px] text-[var(--color-fg-4)]">No events beyond routine occupancy.</p>}
            {signals.map((e) => (
              <button key={e.event_id} onClick={() => seek(e.t)}
                className="grid w-full grid-cols-[44px_1fr_36px] items-center gap-2 px-4 py-1.5 text-left text-[12px] hover:bg-[var(--color-surface-2)]">
                <span className="num text-[var(--color-fg-3)]">{mmss(e.t - start)}</span>
                <span className="truncate text-[var(--color-fg)]">{e.type.replaceAll('_', ' ')}</span>
                <span className="num text-right text-[var(--color-fg-2)]">{e.severity.toFixed(2)}</span>
              </button>
            ))}
          </div>
        </section>
      </aside>
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
