import { describe, expect, it } from 'vitest'
import { camerasFor, clipAt, clipWindow, duration, eventLabel, localTime, nextClipStart, pickPrimary, rankIncidents, scoreColor, severityLabel } from '../lib'
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

describe('main camera', () => {
  const wall = ['G421', 'G419', 'G331']
  const cams = {
    cameras: { G421: { area: 'school' }, G419: { area: 'school' }, G331: { area: 'bus_station' } },
    clips: ['2018-03-15.14-50-00.14-55-00.school.G421', '2018-03-15.15-10-00.15-15-00.bus.G331'],
  } as unknown as SiteConfigView
  const cctv = (sensor_id: string, severity: number) => ({ source: 'cctv', sensor_id, severity })

  it('lists the cameras that saw an incident first, strongest evidence first, then the rest of its area', () => {
    expect(camerasFor({ area: 'school' }, [cctv('G421', 0.4), cctv('G419', 0.8)], cams, wall)).toEqual(['G419', 'G421'])
    expect(camerasFor({ area: 'school' }, [{ source: 'door', sensor_id: 'G331', severity: 1 }], cams, wall)).toEqual(['G421', 'G419'])
    expect(camerasFor(null, [], cams, wall)).toEqual([])
  })
  it('a pinned camera wins; otherwise the incident camera with footage; otherwise any with footage', () => {
    const footage = (c: string) => c === 'G421'
    expect(pickPrimary(wall, 'G331', ['G419', 'G421'], footage)).toEqual({ camera: 'G331', why: 'pinned' })
    expect(pickPrimary(wall, null, ['G419', 'G421'], footage)).toEqual({ camera: 'G421', why: 'incident' })
    expect(pickPrimary(wall, null, ['G419'], footage)).toEqual({ camera: 'G419', why: 'incident' })
    expect(pickPrimary(wall, null, [], footage)).toEqual({ camera: 'G421', why: 'auto' })
  })
  it("finds a camera's next recording", () => {
    expect(nextClipStart(cams, 'G331', 1521139800)).toBe(1521141000)   // 15:10:00
    expect(nextClipStart(cams, 'G331', 1521141000)).toBeNull()
  })
})

describe('plain language', () => {
  it('names signals the way a person would, and falls back readably', () => {
    expect(eventLabel('custody_change')).toBe('Bag taken by someone else')
    expect(eventLabel('some_new_rule')).toBe('Some new rule')
  })
  it('ranks undecided before handled before on-watch, then by risk; drops the rest', () => {
    const list = [
      { id: 'a', status: 'watch', score: 90 }, { id: 'b', status: 'ack', score: 80 },
      { id: 'c', status: 'open', score: 60 }, { id: 'd', status: 'escalated', score: 70 }, { id: 'e', status: 'dismissed', score: 99 },
    ]
    expect(rankIncidents(list).map((i) => i.id)).toEqual(['d', 'c', 'b', 'a'])
  })
  it('formats elapsed time', () => {
    expect(duration(75)).toBe('1:15')
    expect(duration(3725)).toBe('1:02:05')
  })
})

describe('session', () => {
  it('sends the signed-in role, and the supervisor PIN only when there is one', async () => {
    const { authHeaders, setSession } = await import('../lib')
    expect(authHeaders()).toEqual({ 'X-Argus-Role': 'duty_officer' })
    setSession('supervisor', '4821')
    expect(authHeaders()).toEqual({ 'X-Argus-Role': 'supervisor', 'X-Argus-Pin': '4821' })
    setSession('duty_officer')
    expect(authHeaders()).toEqual({ 'X-Argus-Role': 'duty_officer' })
  })
})
