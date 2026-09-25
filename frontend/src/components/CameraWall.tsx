import { useEffect, useRef } from 'react'
import { API, clipAt, clipWindow } from '../lib'
import type { Clock, Incident, SiteConfigView } from '../types'

const WALL = ['G421', 'G419', 'G420', 'G638', 'G336', 'G331']

export function CameraWall({ config, clock, incidents }: { config: SiteConfigView | null; clock: Clock | null; incidents: Incident[] }) {
  if (!config) return null
  const hotAreas = new Set(incidents.filter((i) => ['open', 'escalated'].includes(i.status)).map((i) => i.area))
  return (
    <section className="grid grid-cols-3 gap-2">
      {WALL.filter((c) => config.cameras[c]).map((cam) => (
        <Tile key={cam} camera={cam} config={config} clock={clock} hot={hotAreas.has(config.cameras[cam].area)} />
      ))}
    </section>
  )
}

function Tile({ camera, config, clock, hot }: { camera: string; config: SiteConfigView; clock: Clock | null; hot: boolean }) {
  const video = useRef<HTMLVideoElement>(null)
  const stem = clock ? clipAt(config, camera, clock.sim_t) : null
  const info = config.cameras[camera]

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

  return (
    <div className={`panel relative aspect-video overflow-hidden ${hot ? 'ring-2 ring-[var(--color-high)]' : ''}`}>
      {stem ? (
        <video ref={video} key={stem} src={`${API}/media/${stem}.mp4`} muted playsInline className="h-full w-full object-cover" />
      ) : (
        <div className="flex h-full items-center justify-center text-xs text-[var(--color-dim)]">
          {config.clips.length ? 'No footage for this camera at this time' : 'Footage not loaded (data/meva/web)'}
        </div>
      )}
      <div className="absolute left-0 top-0 flex gap-2 bg-black/60 px-2 py-1 text-[11px]">
        <span className="num font-semibold">{camera}</span>
        <span className="text-[var(--color-mute)]">{info.label}</span>
      </div>
      {hot && <div className="pulse absolute right-2 top-2 h-2.5 w-2.5 rounded-full bg-[var(--color-high)]" />}
    </div>
  )
}
