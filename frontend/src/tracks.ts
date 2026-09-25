import { API } from './lib'

/** One detection from the vision pipeline's track cache (data/tracks/<clip>.jsonl). */
export interface TrackDet {
  frame: number
  tid?: number
  cls: number
  conf: number
  xyxy: [number, number, number, number]
}

export type FrameIndex = Map<number, TrackDet[]>

const cache = new Map<string, Promise<FrameIndex | null>>()

/** Fetch and index a clip's tracks by frame. Resolves null when the clip has no tracks yet. */
export function loadTracks(stem: string): Promise<FrameIndex | null> {
  let p = cache.get(stem)
  if (!p) {
    p = fetch(`${API}/api/tracks/${stem}`)
      .then(async (r) => {
        if (!r.ok) return null
        const index: FrameIndex = new Map()
        for (const line of (await r.text()).split('\n')) {
          if (!line) continue
          const d = JSON.parse(line) as TrackDet
          const list = index.get(d.frame)
          if (list) list.push(d)
          else index.set(d.frame, [d])
        }
        return index
      })
      .catch(() => null)
    cache.set(stem, p)
  }
  return p
}

/** Detections at the tracked frame nearest to `frame` (tracks are sampled every 2nd frame). */
export function detsAt(index: FrameIndex, frame: number): TrackDet[] {
  for (const f of [frame, frame - 1, frame + 1, frame - 2, frame + 2]) {
    const d = index.get(f)
    if (d) return d
  }
  return []
}

export const CLASS_STYLE: Record<number, { label: string; color: string }> = {
  0: { label: 'person', color: '#5aa9e6' },
  2: { label: 'car', color: '#d9b53f' },
  3: { label: 'motorbike', color: '#d9b53f' },
  5: { label: 'bus', color: '#d9b53f' },
  7: { label: 'truck', color: '#d9b53f' },
  24: { label: 'backpack', color: '#f08a3c' },
  26: { label: 'handbag', color: '#f08a3c' },
  28: { label: 'suitcase', color: '#f08a3c' },
  63: { label: 'laptop', color: '#f08a3c' },
  67: { label: 'phone', color: '#f08a3c' },
}
