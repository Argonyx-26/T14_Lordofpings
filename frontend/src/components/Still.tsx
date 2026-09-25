import { useState, type ReactNode } from 'react'
import { API, MOCK } from '../lib'
import type { ArgusEvent } from '../types'

/** Camera events whose rule saw one object in a box (backend/argus/vision/thumbs.py renders a still for them). */
export function hasStill(e: ArgusEvent): boolean {
  const b = e.media?.bbox
  return e.source === 'cctv' && e.type !== 'occupancy' && !!b && b[2] > b[0] && b[3] > b[1]
}

/** The evidence still of an event; hides itself (and its caption) when there is none (mock mode, a clip without stills). */
export function Still({ e, className, job, caption }: { e: ArgusEvent; className: string; job?: string; caption?: ReactNode }) {
  const [failed, setFailed] = useState(false)
  if (failed || MOCK) return null
  const src = job ? `${API}/api/uploads/${job}/thumbs/${e.event_id}.jpg` : `${API}/media/thumbs/${e.event_id}.jpg`
  const img = (
    <img src={src} alt={`${e.type.replaceAll('_', ' ')} on ${e.sensor_id}`} loading="lazy" onError={() => setFailed(true)}
      className={`rounded-[3px] bg-[var(--color-surface-3)] object-cover ${className}`} />
  )
  return caption ? <span className="mb-3 block">{img}{caption}</span> : img
}
