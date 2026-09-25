import { useEffect, useRef, useState } from 'react'
import { API, clipAt, clipWindow } from '../lib'
import { CLASS_STYLE, detsAt, loadTracks, type FrameIndex } from '../tracks'
import type { ArgusEvent, Clock, Incident, SiteConfigView } from '../types'

const WALL = ['G421', 'G419', 'G420', 'G638', 'G336', 'G331']
const HIGHLIGHT_WINDOW_FRAMES = 60 // show an evidence box for ±2 s around its frame
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
  const hotAreas = new Set(incidents.filter((i) => ['open', 'escalated'].includes(i.status)).map((i) => i.area))
  const cams = WALL.filter((c) => config.cameras[c])
  const ordered = focus && cams.includes(focus) ? [focus, ...cams.filter((c) => c !== focus)] : cams

  return (
    <section className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2 px-1">
        <span className="label flex-1">{mode === 'replay' ? 'Camera wall · replay of real MEVA footage' : 'Live inference · YOLO11 + ByteTrack in real time'}</span>
        {mode === 'replay' && (
          <button onClick={() => setBoxes(!boxes)} className="rounded bg-[var(--color-panel-2)] px-2 py-0.5 text-[11px] hover:bg-[var(--color-line)]">
            {boxes ? 'Hide detections' : 'Show detections'}
          </button>
        )}
        <button onClick={() => setMode(mode === 'replay' ? 'live' : 'replay')}
          className={`rounded px-2 py-0.5 text-[11px] ${mode === 'live' ? 'bg-[var(--color-crit)] text-white' : 'bg-[var(--color-panel-2)] hover:bg-[var(--color-line)]'}`}>
          {mode === 'live' ? '● LIVE — back to replay' : 'Live inference'}
        </button>
      </div>
      {mode === 'live' ? (
        <LiveTile />
      ) : (
        <div className="grid grid-cols-3 gap-2">
          {ordered.map((cam) => (
            <Tile key={cam} camera={cam} config={config} clock={clock} boxes={boxes}
              hot={hotAreas.has(config.cameras[cam].area)} focused={cam === focus}
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
  hot: boolean
  focused: boolean
  boxes: boolean
  evidence: ArgusEvent[]
  onClick: () => void
}

function Tile({ camera, config, clock, hot, focused, boxes, evidence, onClick }: TileProps) {
  const video = useRef<HTMLVideoElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const [tracks, setTracks] = useState<FrameIndex | null>(null)
  const stem = clock ? clipAt(config, camera, clock.sim_t) : null
  const info = config.cameras[camera]

  useEffect(() => {
    setTracks(null)
    if (stem) loadTracks(stem).then(setTracks)
  }, [stem])

  // Keep the <video> in step with the replay clock: seek when drift > 1.5 s, mirror play/pause and speed.
  useEffect(() => {
    const v = video.current
    if (!v || !stem || !clock) return
    const target = clock.sim_t - clipWindow(stem).start
    if (Math.abs(v.currentTime - target) > 1.5) v.currentTime = target
    v.playbackRate = Math.min(clock.speed, 16)
    if (clock.playing && v.paused) v.play().catch(() => {})
    if (!clock.playing && !v.paused) v.pause()
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
      const frame = Math.round(v.currentTime * config.fps)
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

  return (
    <div onClick={onClick}
      className={`panel relative cursor-pointer overflow-hidden bg-black ${focused ? 'col-span-2 row-span-2' : ''} ${hot ? 'ring-2 ring-[var(--color-high)]' : ''}`}
      style={{ aspectRatio: '16 / 9' }}>
      {stem ? (
        <>
          <video ref={video} key={stem} src={`${API}/media/${stem}.mp4`} muted playsInline className="absolute inset-0 h-full w-full object-contain" />
          <canvas ref={canvas} className="pointer-events-none absolute inset-0 h-full w-full" />
        </>
      ) : (
        <div className="flex h-full items-center justify-center text-xs text-[var(--color-dim)]">
          {config.clips.length ? 'No footage for this camera at this time' : 'Footage not loaded (data/meva/web)'}
        </div>
      )}
      <div className="absolute left-0 top-0 flex gap-2 bg-black/60 px-2 py-1 text-[11px]">
        <span className="num font-semibold">{camera}</span>
        <span className="text-[var(--color-mute)]">{info.label}</span>
        {stem && !tracks && <span className="text-[var(--color-dim)]">no tracks</span>}
      </div>
      {hot && <div className="pulse absolute right-2 top-2 h-2.5 w-2.5 rounded-full bg-[var(--color-high)]" />}
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
      <div className="panel flex aspect-video items-center justify-center p-6 text-center text-sm text-[var(--color-dim)]">
        Live inference is not running. Start it with <code className="mx-1 text-[var(--color-ink)]">scripts\run_demo.ps1 -Live</code>
      </div>
    )
  }
  return (
    <div className="panel relative overflow-hidden bg-black">
      <img src={`${LIVE_URL}/live.mjpg`} alt="Live inference stream" className="aspect-video w-full object-contain" />
      <div className="absolute left-0 top-0 flex items-center gap-3 bg-black/70 px-2 py-1 text-[11px]">
        <span className="pulse h-2 w-2 rounded-full bg-[var(--color-crit)]" />
        <span className="font-semibold">LIVE</span>
        <span className="text-[var(--color-mute)]">{stats?.source}</span>
        <span className="num">{stats?.fps ?? '–'} fps</span>
        <span className="num text-[var(--color-mute)]">{stats?.infer_ms ?? '–'} ms/frame</span>
        {Object.entries(stats?.counts ?? {}).map(([k, v]) => (
          <span key={k} className="num text-[var(--color-mute)]">{k} {v}</span>
        ))}
      </div>
    </div>
  )
}
