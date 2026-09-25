import { Eye, EyeOff, Radio } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { API, clipAt, clipWindow, scoreColor } from '../lib'
import { CLASS_STYLE, detsAt, loadTracks, type FrameIndex } from '../tracks'
import type { ArgusEvent, Clock, Incident, SiteConfigView } from '../types'

const WALL = ['G421', 'G419', 'G420', 'G638', 'G336', 'G331']
const HIGHLIGHT_WINDOW_FRAMES = 60 // show an evidence box for ±2 s around its frame
// At 10x six 30 fps tiles need 1,800 decoded frames/s and the browser falls to ~0.2x; at 5x it manages ~4.3x
// (measured). From 4x up tiles play a 5 fps proxy of the same clip (media/fast/, made by run_demo.ps1). A 60 Hz
// screen shows at most 60 frames/s per tile either way.
const FAST_SPEED = 4
export const LIVE_URL = import.meta.env.VITE_ARGUS_LIVE ?? `${location.protocol}//${location.hostname}:8001`

interface Props {
  config: SiteConfigView | null
  clock: Clock | null
  incidents: Incident[]
  evidence: ArgusEvent[]
  focus: string | null
  onFocus: (camera: string | null) => void
}

export function CameraWall({ config, clock, incidents, evidence, focus, onFocus }: Props) {
  const [mode, setMode] = useState<'replay' | 'live'>('replay')
  const [boxes, setBoxes] = useState(true)
  if (!config) return null
  const hot = new Map<string, Incident>()
  for (const i of incidents) {
    if (!['open', 'escalated', 'ack'].includes(i.status)) continue
    const prev = hot.get(i.area)
    if (!prev || i.score > prev.score) hot.set(i.area, i)
  }
  const cams = WALL.filter((c) => config.cameras[c])
  const ordered = focus && cams.includes(focus) ? [focus, ...cams.filter((c) => c !== focus)] : cams

  return (
    <section className="flex flex-col gap-2">
      <div className="flex h-7 items-center gap-3">
        <span className="text-[13px] font-medium text-[var(--color-fg)]">Cameras</span>
        <span className="text-[11px] text-[var(--color-fg-3)]">
          {mode === 'replay' ? 'Replay of real MEVA footage · click a camera to enlarge' : 'Real-time YOLO11 + ByteTrack on this laptop\'s GPU'}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {mode === 'replay' && (
            <button className="btn" onClick={() => setBoxes(!boxes)}>
              {boxes ? <Eye size={13} strokeWidth={1.75} /> : <EyeOff size={13} strokeWidth={1.75} />} Detections
            </button>
          )}
          <button className={`btn ${mode === 'live' ? 'border-[var(--color-crit)] text-[var(--color-fg)]' : ''}`}
            onClick={() => setMode(mode === 'replay' ? 'live' : 'replay')}>
            <Radio size={13} strokeWidth={1.75} className={mode === 'live' ? 'text-[var(--color-crit)] breathe' : ''} />
            {mode === 'live' ? 'Live · back to replay' : 'Live inference'}
          </button>
        </div>
      </div>
      {mode === 'live' ? (
        <LiveTile />
      ) : (
        <div className="grid grid-cols-3 gap-1.5">
          {ordered.map((cam) => (
            <Tile key={cam} camera={cam} config={config} clock={clock} boxes={boxes}
              incident={hot.get(config.cameras[cam].area) ?? null} focused={cam === focus}
              evidence={evidence.filter((e) => e.source === 'cctv' && e.sensor_id === cam && e.media?.bbox)}
              onClick={() => onFocus(cam === focus ? null : cam)} />
          ))}
        </div>
      )}
    </section>
  )
}

interface TileProps {
  camera: string
  config: SiteConfigView
  clock: Clock | null
  incident: Incident | null
  focused: boolean
  boxes: boolean
  evidence: ArgusEvent[]
  onClick: () => void
}

function Tile({ camera, config, clock, incident, focused, boxes, evidence, onClick }: TileProps) {
  const video = useRef<HTMLVideoElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const [tracks, setTracks] = useState<FrameIndex | null>(null)
  const [noProxy, setNoProxy] = useState(false)
  const shownT = useRef<number | null>(null)   // media time of the frame actually on screen
  const stem = clock ? clipAt(config, camera, clock.sim_t) : null
  const fast = !!clock && clock.speed >= FAST_SPEED && !noProxy
  const info = config.cameras[camera]

  // Track the presented frame (requestVideoFrameCallback), so boxes match the picture even when the decoder
  // runs behind currentTime at high speed.
  useEffect(() => {
    const v = video.current
    shownT.current = null
    if (!v || !('requestVideoFrameCallback' in v)) return
    let id = 0
    const cb = (_now: number, meta: VideoFrameCallbackMetadata) => {
      shownT.current = meta.mediaTime
      id = v.requestVideoFrameCallback(cb)
    }
    id = v.requestVideoFrameCallback(cb)
    return () => v.cancelVideoFrameCallback(id)
  }, [stem, fast])

  useEffect(() => {
    setTracks(null)
    if (stem) loadTracks(stem).then(setTracks)
  }, [stem])

  // Keep the <video> in step with the replay clock. Small drift is absorbed by nudging playbackRate; only a
  // real jump seeks, and never while a seek is in flight. (Seeking whenever drift > 1.5 s re-seeked on every
  // 0.25 s tick at 5-10x, since each tick moves the clock 1.25-2.5 s: the video sat paused mid-seek, a slideshow.)
  useEffect(() => {
    const v = video.current
    if (!v || !stem || !clock) return
    if (!clock.playing && !v.paused) v.pause()
    if (v.seeking) return
    const target = clock.sim_t - clipWindow(stem).start
    const drift = v.currentTime - target                             // > 0: video ahead of the clock
    const tol = clock.playing ? Math.max(2, clock.speed) : 0.5       // one real second of footage at speed
    if (Math.abs(drift) > tol) {
      v.currentTime = target
      return                                                         // play resumes on a later tick
    }
    const nudge = Math.max(-0.3, Math.min(0.3, -drift / tol))
    v.playbackRate = Math.max(0.25, Math.min(16, Math.min(clock.speed, 16) * (1 + nudge)))
    if (clock.playing && v.paused) v.play().catch(() => {})
  }, [clock, stem])

  // Draw detection boxes and evidence highlights for the frame currently on screen.
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
      // Boxes are in original 1920-wide pixels; the <video> is object-contain, so letterbox offsets apply.
      const origW = 1920
      const origH = origW * (v.videoHeight / v.videoWidth)
      const s = Math.min(W / origW, H / origH)
      const ox = (W - origW * s) / 2
      const oy = (H - origH * s) / 2
      const frame = Math.round((shownT.current ?? v.currentTime) * config.fps)
      const rect = (b: number[]) => [ox + b[0] * s, oy + b[1] * s, (b[2] - b[0]) * s, (b[3] - b[1]) * s] as const

      if (boxes && tracks) {
        ctx.lineWidth = 1.5
        ctx.font = '10px ui-monospace, monospace'
        for (const d of detsAt(tracks, frame)) {
          const st = CLASS_STYLE[d.cls] ?? { label: String(d.cls), color: '#aaa' }
          const [x, y, w, h] = rect(d.xyxy)
          ctx.strokeStyle = st.color
          ctx.strokeRect(x, y, w, h)
          if (focused) {
            ctx.fillStyle = st.color
            ctx.fillText(`${st.label}${d.tid !== undefined ? ' #' + d.tid : ''}`, x + 2, y - 3)
          }
        }
      }
      for (const e of evidence) {
        if (!e.media?.bbox || Math.abs(e.media.frame - frame) > HIGHLIGHT_WINDOW_FRAMES) continue
        if (stem && e.media.clip !== stem) continue
        const [x, y, w, h] = rect(e.media.bbox)
        ctx.lineWidth = 3
        ctx.strokeStyle = '#ef4f4f'
        ctx.strokeRect(x - 3, y - 3, w + 6, h + 6)
        ctx.fillStyle = '#ef4f4f'
        ctx.font = 'bold 12px ui-sans-serif, system-ui'
        ctx.fillText(e.type.replaceAll('_', ' '), x - 3, y - 8)
      }
    }
    raf = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(raf)
  }, [tracks, boxes, evidence, focused, stem, config.fps])

  const accent = incident ? scoreColor(incident.score, config) : null
  return (
    <div onClick={onClick}
      className={`group relative cursor-pointer overflow-hidden rounded-md bg-black ${focused ? 'col-span-2 row-span-2' : ''}`}
      style={{ aspectRatio: '16 / 9', boxShadow: accent ? `inset 0 0 0 1.5px ${accent}` : 'inset 0 0 0 1px var(--color-hair)' }}>
      {stem ? (
        <>
          <video ref={video} key={`${stem}${fast ? ':fast' : ''}`} src={`${API}/media/${fast ? 'fast/' : ''}${stem}.mp4`}
            onError={() => fast && setNoProxy(true)} muted playsInline className="absolute inset-0 h-full w-full object-contain" />
          <canvas ref={canvas} className="pointer-events-none absolute inset-0 h-full w-full" />
        </>
      ) : (
        <div className="flex h-full items-center justify-center px-4 text-center text-[11px] text-[var(--color-fg-4)]">
          {config.clips.length ? 'No recording at this moment' : 'Footage not loaded'}
        </div>
      )}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end gap-2 bg-gradient-to-t from-black/80 to-transparent px-2.5 pb-1.5 pt-6">
        <span className="num text-[11px] font-medium text-[var(--color-fg)]">{camera}</span>
        <span className="truncate text-[11px] text-[var(--color-fg-2)]">{info.label}</span>
        {stem && !tracks && <span className="ml-auto text-[10px] text-[var(--color-fg-4)]">no detections cached</span>}
      </div>
      {incident && accent && (
        <div className="absolute right-1.5 top-1.5 flex items-center gap-1.5 rounded bg-black/70 px-1.5 py-0.5 text-[10.5px]">
          <span className="h-1.5 w-1.5 rounded-full breathe" style={{ background: accent }} />
          <span className="num" style={{ color: accent }}>{incident.score}</span>
          <span className="text-[var(--color-fg-2)]">{incident.incident_id}</span>
        </div>
      )}
    </div>
  )
}

interface LiveStats { fps: number; infer_ms: number; counts: Record<string, number>; source: string; running: boolean }

function LiveTile() {
  const [stats, setStats] = useState<LiveStats | null>(null)
  const [down, setDown] = useState(false)
  useEffect(() => {
    const poll = () =>
      fetch(`${LIVE_URL}/live/stats`)
        .then((r) => r.json())
        .then((s) => { setStats(s); setDown(false) })
        .catch(() => setDown(true))
    poll()
    const id = setInterval(poll, 1000)
    return () => clearInterval(id)
  }, [])

  if (down) {
    return (
      <div className="flex aspect-video flex-col items-center justify-center gap-2 rounded-md text-center" style={{ boxShadow: 'inset 0 0 0 1px var(--color-hair)' }}>
        <Radio size={18} strokeWidth={1.5} className="text-[var(--color-fg-4)]" />
        <span className="text-[12px] text-[var(--color-fg-2)]">Live inference isn't running</span>
        <span className="num text-[11px] text-[var(--color-fg-4)]">scripts\run_demo.ps1 -Live</span>
      </div>
    )
  }
  return (
    <div className="relative overflow-hidden rounded-md bg-black" style={{ boxShadow: 'inset 0 0 0 1px var(--color-hair)' }}>
      <img src={`${LIVE_URL}/live.mjpg`} alt="Live inference stream" className="aspect-video w-full object-contain" />
      <div className="absolute inset-x-0 top-0 flex items-center gap-4 bg-gradient-to-b from-black/80 to-transparent px-3 pb-6 pt-2 text-[11px]">
        <span className="flex items-center gap-1.5 font-medium text-[var(--color-fg)]">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-crit)] breathe" /> LIVE
        </span>
        <span className="text-[var(--color-fg-2)]">{stats?.source}</span>
        <span className="num ml-auto text-[var(--color-fg)]">{stats?.fps ?? '–'} <span className="text-[var(--color-fg-3)]">fps</span></span>
        <span className="num text-[var(--color-fg)]">{stats?.infer_ms ?? '–'} <span className="text-[var(--color-fg-3)]">ms / frame</span></span>
        {Object.entries(stats?.counts ?? {}).map(([k, v]) => (
          <span key={k} className="num text-[var(--color-fg)]">{v} <span className="text-[var(--color-fg-3)]">{k}</span></span>
        ))}
      </div>
    </div>
  )
}
