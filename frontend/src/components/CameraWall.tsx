import { Eye, EyeOff, Pin, PinOff, Radio, SkipForward, VideoOff } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { API, LEVEL_COLOR, MOCK, WALL, camerasFor, clipAt, clipWindow, eventLabel, isActive, levelOf, localTime, nextClipStart, pickPrimary, post } from '../lib'
import { CLASS_STYLE, detsAt, loadTracks, type FrameIndex } from '../tracks'
import type { ArgusEvent, Clock, Incident, SiteConfigView } from '../types'
import { Still, hasStill } from './Still'
import { StatusSymbol } from './Symbols'

const HIGHLIGHT_WINDOW_FRAMES = 60 // show an evidence box for ±2 s around its frame
// At 10x six 30 fps tiles need 1,800 decoded frames/s and the browser falls to ~0.2x; at 5x it manages ~4.3x
// (measured). From 4x up tiles play a 5 fps proxy of the same clip (media/fast/, made by run_demo.ps1). A 60 Hz
// screen shows at most 60 frames/s per tile either way.
const FAST_SPEED = 4
export const LIVE_URL = import.meta.env.VITE_ARGUS_LIVE ?? `${location.protocol}//${location.hostname}:8001`
const EVIDENCE_RED = '#ff5a5a'

interface Props {
  config: SiteConfigView | null
  clock: Clock | null
  incidents: Incident[]
  current: Incident | null
  evidence: ArgusEvent[]
  focus: string | null
  onFocus: (camera: string | null) => void
}

/**
 * One main camera and the rest in a filmstrip. The main camera follows the incident in front of the operator
 * (the way a VMS alarm pops the nearest camera) until they pin another. Tiles never remount when they swap
 * places, so switching is instant and video keeps playing.
 */
export function CameraWall({ config, clock, incidents, current, evidence, focus, onFocus }: Props) {
  const [mode, setMode] = useState<'replay' | 'live'>('replay')
  const [boxes, setBoxes] = useState(true)

  // camera evidence per camera, stable between ticks so the overlay loops don't restart
  const byCamera = useMemo(() => {
    const m = new Map<string, ArgusEvent[]>()
    for (const e of evidence) {
      if (e.source !== 'cctv' || !e.media?.bbox) continue
      const list = m.get(e.sensor_id)
      if (list) list.push(e)
      else m.set(e.sensor_id, [e])
    }
    return m
  }, [evidence])

  if (!config) return <section className="surface fill-sm flex-1" />
  const cams = WALL.filter((c) => config.cameras[c])
  const hot = new Map<string, Incident>()
  for (const i of incidents) {
    if (!isActive(i.status)) continue
    const prev = hot.get(i.area)
    if (!prev || i.score > prev.score) hot.set(i.area, i)
  }
  const hasFootage = (c: string) => !!clock && !!clipAt(config, c, clock.sim_t)
  const { camera: primary, why } = pickPrimary(cams, focus, camerasFor(current, evidence, config, cams), hasFootage)
  const info = config.cameras[primary]
  const others = cams.filter((c) => c !== primary)

  return (
    <section className="surface fill-sm flex min-h-0 flex-1 flex-col overflow-hidden">
      <div className="flex h-11 shrink-0 items-center gap-2.5 px-3.5 hairline-b">
        {mode === 'live' ? (
          <span className="flex items-center gap-2 text-[13px] font-medium">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--color-crit)] breathe" /> Live inference
            <span className="hidden text-[11.5px] font-normal text-[var(--color-fg-3)] md:inline">YOLO11 + ByteTrack running on this laptop's GPU right now</span>
          </span>
        ) : (
          <>
            <span className="num text-[13px] font-medium text-[var(--color-fg)]">{primary}</span>
            <span className="truncate text-[13px] text-[var(--color-fg-2)]">{info.label}</span>
            <span className="hidden truncate text-[11.5px] text-[var(--color-fg-4)] md:inline">· {config.areas[info.area]?.name ?? info.area}</span>
            {why === 'incident' && current && (
              <span className="chip hidden md:inline-flex" style={{ color: 'var(--color-accent)' }} title="The main view follows the selected incident">
                Following {current.incident_id}
              </span>
            )}
            {why === 'pinned' && (
              <button className="chip transition hover:text-[var(--color-fg)]" onClick={() => onFocus(null)} title="Let the main view follow incidents again">
                <Pin size={11} /> Pinned · <PinOff size={11} /> follow incidents
              </button>
            )}
          </>
        )}
        <div className="ml-auto flex items-center gap-1.5">
          {mode === 'replay' && (
            <button className="btn btn-sm" data-on={boxes} onClick={() => setBoxes(!boxes)} aria-pressed={boxes}
              title="Draw what the detector sees: people, vehicles and bags">
              {boxes ? <Eye size={13} strokeWidth={1.75} /> : <EyeOff size={13} strokeWidth={1.75} />}
              <span className="hidden sm:inline">Detections</span>
            </button>
          )}
          <button className="btn btn-sm" data-on={mode === 'live'} onClick={() => setMode(mode === 'replay' ? 'live' : 'replay')}
            title="Switch to the detector running live on this laptop">
            <Radio size={13} strokeWidth={1.75} className={mode === 'live' ? 'text-[var(--color-crit)]' : ''} />
            <span className="hidden sm:inline">{mode === 'live' ? 'Back to replay' : 'Live inference'}</span>
          </button>
        </div>
      </div>

      {mode === 'live' ? (
        <LiveTile />
      ) : (
        <div className="feed-grid min-h-0 flex-1 gap-1.5 p-1.5" style={{ gridTemplateColumns: `repeat(${Math.max(1, others.length)}, minmax(0, 1fr))` }}>
          {cams.map((cam) => (
            <Tile key={cam} camera={cam} config={config} clock={clock} boxes={boxes} primary={cam === primary}
              order={cam === primary ? -1 : others.indexOf(cam)}
              incident={hot.get(config.cameras[cam].area) ?? null}
              evidence={byCamera.get(cam) ?? NONE}
              onClick={() => cam !== primary && onFocus(cam)} />
          ))}
        </div>
      )}
    </section>
  )
}

const NONE: ArgusEvent[] = []

interface TileProps {
  camera: string
  config: SiteConfigView
  clock: Clock | null
  incident: Incident | null
  primary: boolean
  order: number
  boxes: boolean
  evidence: ArgusEvent[]
  onClick: () => void
}

function Tile({ camera, config, clock, incident, primary, order, boxes, evidence, onClick }: TileProps) {
  const video = useRef<HTMLVideoElement>(null)
  const canvas = useRef<HTMLCanvasElement>(null)
  const counts = useRef<HTMLSpanElement>(null)
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

  // Overlay: detection boxes (main view only; unreadable in a thumbnail) and evidence highlights. Redraws only
  // when the frame on screen or the tile size changes, and stops altogether when there is nothing to draw.
  useEffect(() => {
    const c = canvas.current
    const drawBoxes = boxes && primary && !!tracks
    if (!c) return
    if (!drawBoxes && !evidence.length) {
      c.getContext('2d')?.clearRect(0, 0, c.width, c.height)
      if (counts.current) counts.current.textContent = ''
      return
    }
    const ctx = c.getContext('2d')!
    let raf = 0
    let last = ''
    const draw = () => {
      raf = requestAnimationFrame(draw)
      const v = video.current
      if (!v || !v.videoWidth) return
      const W = c.clientWidth
      const H = c.clientHeight
      const frame = Math.round((shownT.current ?? v.currentTime) * config.fps)
      const key = `${frame}|${W}|${H}`
      if (key === last) return
      last = key
      if (c.width !== W || c.height !== H) { c.width = W; c.height = H }
      ctx.clearRect(0, 0, W, H)
      // Boxes are in original 1920-wide pixels; the <video> is object-contain, so letterbox offsets apply.
      const origW = 1920
      const origH = origW * (v.videoHeight / v.videoWidth)
      const s = Math.min(W / origW, H / origH)
      const ox = (W - origW * s) / 2
      const oy = (H - origH * s) / 2
      const rect = (b: number[]) => [ox + b[0] * s, oy + b[1] * s, (b[2] - b[0]) * s, (b[3] - b[1]) * s] as const

      if (drawBoxes) {
        const dets = detsAt(tracks!, frame)
        ctx.lineWidth = 1.5
        ctx.font = '500 10.5px "Geist Mono Variable", ui-monospace, monospace'
        const n = { people: 0, vehicles: 0, bags: 0, devices: 0 }
        for (const d of dets) {
          const st = CLASS_STYLE[d.cls] ?? { label: String(d.cls), color: '#aaa' }
          const [x, y, w, h] = rect(d.xyxy)
          ctx.strokeStyle = st.color
          ctx.globalAlpha = 0.9
          ctx.strokeRect(x, y, w, h)
          ctx.globalAlpha = 1
          ctx.fillStyle = st.color
          ctx.fillText(`${st.label}${d.tid !== undefined ? ' ' + d.tid : ''}`, x + 2, y - 4)
          if (d.cls === 0) n.people++
          else if ([2, 3, 5, 7].includes(d.cls)) n.vehicles++
          else if ([24, 26, 28].includes(d.cls)) n.bags++
          else if ([63, 67].includes(d.cls)) n.devices++
        }
        if (counts.current) {
          counts.current.textContent = [
            plural(n.people, 'person', 'people'), plural(n.vehicles, 'vehicle'), plural(n.bags, 'bag'), plural(n.devices, 'device'),
          ].filter(Boolean).join('  ·  ') || 'nobody in view'
        }
      } else if (counts.current) counts.current.textContent = ''

      for (const e of evidence) {
        if (!e.media?.bbox || Math.abs(e.media.frame - frame) > HIGHLIGHT_WINDOW_FRAMES) continue
        if (stem && e.media.clip !== stem) continue
        const [x, y, w, h] = rect(e.media.bbox)
        const pad = primary ? 4 : 2
        ctx.lineWidth = primary ? 2.5 : 2
        ctx.strokeStyle = EVIDENCE_RED
        ctx.strokeRect(x - pad, y - pad, w + 2 * pad, h + 2 * pad)
        if (primary) {
          const label = eventLabel(e.type)
          ctx.font = '600 12px "Geist Variable", ui-sans-serif, system-ui'
          const tw = ctx.measureText(label).width
          const lx = Math.max(0, Math.min(x - pad, W - tw - 12))   // keep the tag inside the frame
          const ly = y - pad - 20 < 0 ? y + h + pad + 2 : y - pad - 20
          ctx.fillStyle = EVIDENCE_RED
          ctx.fillRect(lx, ly, tw + 12, 18)
          ctx.fillStyle = '#fff'
          ctx.fillText(label, lx + 6, ly + 13)
        }
      }
    }
    raf = requestAnimationFrame(draw)
    return () => cancelAnimationFrame(raf)
  }, [tracks, boxes, evidence, primary, stem, config.fps])

  const level = incident ? levelOf(incident.score, config) : null
  const accent = level ? LEVEL_COLOR[level] : null
  const next = !stem && clock ? nextClipStart(config, camera, clock.sim_t) : null
  const still = !stem ? evidence.find(hasStill) : undefined

  return (
    <div onClick={onClick} role={primary ? undefined : 'button'} tabIndex={primary ? undefined : 0}
      onKeyDown={(e) => !primary && (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), onClick())}
      aria-label={primary ? `${camera} ${info.label}, main view` : `Show ${camera} ${info.label} in the main view`}
      className={`group relative overflow-hidden rounded-md bg-black ${primary ? 'tile-primary' : 'cursor-pointer'}`}
      style={{
        order, gridColumn: primary ? '1 / -1' : undefined, aspectRatio: primary ? undefined : '16 / 9',
        boxShadow: accent ? `inset 0 0 0 1.5px ${accent}` : 'inset 0 0 0 1px var(--color-hair)',
      }}>
      {stem ? (
        <>
          <video ref={video} key={`${stem}${fast ? ':fast' : ''}`} src={`${API}/media/${fast ? 'fast/' : ''}${stem}.mp4`}
            onError={() => fast && setNoProxy(true)} muted playsInline
            className={`absolute inset-0 h-full w-full object-contain transition-opacity ${primary ? '' : 'opacity-80 group-hover:opacity-100'}`} />
          <canvas ref={canvas} className="pointer-events-none absolute inset-0 h-full w-full" />
        </>
      ) : (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 px-3 text-center" style={{ background: 'var(--color-surface-2)' }}>
          {still && primary && <Still e={still} className="absolute inset-0 h-full w-full opacity-30" />}
          <VideoOff size={primary ? 20 : 13} strokeWidth={1.5} className="relative text-[var(--color-fg-4)]" />
          {primary ? (
            <div className="relative">
              <div className="text-[13px] text-[var(--color-fg-2)]">
                {config.clips.length ? `No recording from ${camera} at ${clock ? localTime(clock.sim_t) : 'this moment'}` : "This camera's footage isn't on this machine"}
              </div>
              {next !== null && (
                <button className="btn btn-sm mx-auto mt-3" disabled={MOCK}
                  onClick={(e) => { e.stopPropagation(); post('/api/replay', { cmd: 'seek', value: next }).catch(console.error) }}>
                  <SkipForward size={13} strokeWidth={1.75} /> Jump to its next recording · <span className="num">{localTime(next)}</span>
                </button>
              )}
            </div>
          ) : (
            <span className="relative hidden text-[10.5px] text-[var(--color-fg-4)] sm:inline">{config.clips.length ? 'No footage now' : 'No footage'}</span>
          )}
        </div>
      )}

      {/* identity (the main view is named in the panel header) */}
      {!primary && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end gap-1.5 bg-gradient-to-t from-black/85 to-transparent px-2 pb-1 pt-5">
          <span className="num text-[10.5px] font-medium text-white">{camera}</span>
          <span className="truncate text-[10.5px] text-white/65">{info.label}</span>
        </div>
      )}

      {/* the incident this camera's area is part of */}
      {incident && level && (
        primary ? (
          <div className="pointer-events-none absolute left-2.5 top-2.5 flex items-center gap-2 glass rounded-md px-2 py-1 text-[11.5px]">
            <StatusSymbol level={level} size={9} pulse={incident.status === 'open'} />
            <span className="num font-medium" style={{ color: accent! }}>{incident.score}</span>
            <span className="max-w-[260px] truncate text-white/85">{incident.title.split(' — ')[0]}</span>
          </div>
        ) : (
          <div className="pointer-events-none absolute right-1 top-1 flex items-center gap-1 rounded bg-black/70 px-1 py-px text-[10px]">
            <StatusSymbol level={level} size={7} pulse={incident.status === 'open'} />
            <span className="num" style={{ color: accent! }}>{incident.score}</span>
          </div>
        )
      )}

      {/* what the detector sees right now, and the key to the boxes */}
      {primary && stem && boxes && (
        <div className="pointer-events-none absolute inset-x-2.5 bottom-2.5 flex items-end justify-between gap-3">
          {tracks ? <span ref={counts} className="num glass rounded-md px-2 py-1 text-[11.5px] text-white/90 empty:hidden" />
            : <span className="glass rounded-md px-2 py-1 text-[11px] text-white/60">No detections cached for this clip</span>}
          <span className="hidden items-center gap-2.5 glass rounded-md px-2 py-1 text-[10.5px] text-white/75 md:flex">
            <Key color={CLASS_STYLE[0].color} label="person" />
            <Key color={CLASS_STYLE[2].color} label="vehicle" />
            <Key color={CLASS_STYLE[24].color} label="bag / device" />
            <Key color={EVIDENCE_RED} label="evidence" thick />
          </span>
        </div>
      )}
    </div>
  )
}

function Key({ color, label, thick }: { color: string; label: string; thick?: boolean }) {
  return (
    <span className="flex items-center gap-1">
      <span className="inline-block h-2 w-2.5 rounded-[2px]" style={{ boxShadow: `inset 0 0 0 ${thick ? 2 : 1.25}px ${color}` }} />
      {label}
    </span>
  )
}

const plural = (n: number, one: string, many = one + 's') => (n ? `${n} ${n === 1 ? one : many}` : '')

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
      <div className="flex min-h-[240px] flex-1 flex-col items-center justify-center gap-2 text-center">
        <Radio size={20} strokeWidth={1.5} className="text-[var(--color-fg-4)]" />
        <span className="text-[13px] text-[var(--color-fg-2)]">Live inference isn't running on this machine</span>
        <span className="num text-[11px] text-[var(--color-fg-4)]">scripts\run_demo.ps1 -Live</span>
      </div>
    )
  }
  return (
    <div className="relative min-h-[240px] flex-1 overflow-hidden bg-black">
      <img src={`${LIVE_URL}/live.mjpg`} alt="Live inference stream" className="absolute inset-0 h-full w-full object-contain" />
      <div className="absolute inset-x-0 top-0 flex flex-wrap items-center gap-x-4 gap-y-1 bg-gradient-to-b from-black/80 to-transparent px-3 pb-6 pt-2 text-[11.5px]">
        <span className="text-white/70">{stats?.source}</span>
        <span className="num ml-auto text-white">{stats?.fps ?? '–'} <span className="text-white/55">fps</span></span>
        <span className="num text-white">{stats?.infer_ms ?? '–'} <span className="text-white/55">ms / frame</span></span>
        {Object.entries(stats?.counts ?? {}).map(([k, v]) => (
          <span key={k} className="num text-white">{v} <span className="text-white/55">{k}</span></span>
        ))}
      </div>
    </div>
  )
}
