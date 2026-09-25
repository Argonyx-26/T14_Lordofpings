import { describe, expect, it } from 'vitest'
import { clipAt, clipWindow, localTime, scoreColor, severityLabel } from '../lib'
import { detsAt, type FrameIndex } from '../tracks'
import type { SiteConfigView } from '../types'

const cfg = {
  thresholds: { watch_threshold: 35, open_threshold: 55, siloed_alert_severity: 0.25, context_max_severity: 0.2 },
  clips: ['2018-03-15.14-50-00.14-55-00.school.G421', '2018-03-15.15-10-00.15-15-00.bus.G331'],
} as unknown as SiteConfigView

describe('clip maths', () => {
  it('parses a MEVA clip name into UTC epoch seconds (site time is UTC-4)', () => {
    const w = clipWindow('2018-03-15.14-50-01.14-55-01.school.G420')
    expect(w.camera).toBe('G420')
    expect(w.start).toBe(1521139801)            // 14:50:01 EDT == 18:50:01 UTC
    expect(w.end - w.start).toBe(300)
  })
  it('finds the clip covering a moment, and none in a gap', () => {
    expect(clipAt(cfg, 'G421', 1521139800 + 60)).toBe('2018-03-15.14-50-00.14-55-00.school.G421')
    expect(clipAt(cfg, 'G331', 1521139800 + 60)).toBeNull()
    expect(clipAt(cfg, 'G421', 1521139800 + 300)).toBeNull()   // end is exclusive
  })
  it('shows site-local time', () => {
    expect(localTime(1521139800)).toBe('14:50:00')
  })
})

describe('severity', () => {
  it('maps scores to the same bands as the backend thresholds', () => {
    expect(severityLabel(20, cfg)).toBe('Low')
    expect(severityLabel(35, cfg)).toBe('Watch')
    expect(severityLabel(55, cfg)).toBe('High')
    expect(severityLabel(75, cfg)).toBe('Critical')
    expect(scoreColor(80, cfg)).toBe('var(--color-crit)')
  })
})

describe('detections lookup', () => {
  it('uses the nearest tracked frame (tracks are every 2nd frame)', () => {
    const idx: FrameIndex = new Map([[100, [{ frame: 100, cls: 0, conf: 0.9, xyxy: [0, 0, 1, 1] }]]])
    expect(detsAt(idx, 101)).toHaveLength(1)
    expect(detsAt(idx, 102)).toHaveLength(1)
    expect(detsAt(idx, 110)).toHaveLength(0)
  })
})
