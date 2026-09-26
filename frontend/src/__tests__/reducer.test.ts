import { describe, expect, it } from 'vitest'
import type { ArgusEvent, Incident, Tick } from '../types'
import { initial, reducer } from '../useArgus'

const ev = (i: number) => ({ event_id: `e${i}`, t: i } as unknown as ArgusEvent)
const inc = (id: string, score: number) => ({ incident_id: id, score } as unknown as Incident)
const tick = (events: ArgusEvent[], incidents: Incident[]): Tick =>
  ({ type: 'tick', clock: {} as Tick['clock'], summary: {} as Tick['summary'], events, incidents })

describe('live state reducer', () => {
  it('merges incident updates by id and keeps the rest', () => {
    let s = reducer(initial, { kind: 'tick', tick: tick([], [inc('INC-1', 40), inc('INC-2', 60)]) })
    s = reducer(s, { kind: 'tick', tick: tick([], [inc('INC-1', 70)]) })
    expect(s.incidents['INC-1'].score).toBe(70)
    expect(s.incidents['INC-2'].score).toBe(60)
  })
  it('caps the event buffer so a long replay never grows memory', () => {
    let s = initial
    for (let k = 0; k < 10; k++) s = reducer(s, { kind: 'tick', tick: tick(Array.from({ length: 100 }, (_, i) => ev(k * 100 + i)), []) })
    expect(s.events).toHaveLength(400)
    expect(s.events[399].event_id).toBe('e999')
  })
  it('a snapshot replaces incidents wholesale (seek back / reset)', () => {
    let s = reducer(initial, { kind: 'tick', tick: tick([], [inc('INC-9', 90)]) })
    s = reducer(s, { kind: 'snapshot', snap: { type: 'snapshot', clock: {} as Tick['clock'], summary: {} as Tick['summary'], incidents: [inc('INC-1', 10)], recent_events: [] } })
    expect(Object.keys(s.incidents)).toEqual(['INC-1'])
  })
})

describe('placeholders', () => {
  it('counts distinct stand-in events in a snapshot, wherever they appear', async () => {
    const { placeholders } = await import('../useArgus')
    const ev = (id: string, fixture?: boolean) => ({ event_id: id, attrs: fixture ? { fixture: true } : {} }) as never
    const snap = { recent_events: [ev('a', true), ev('b')], evidence: { 'INC-1': [ev('a', true), ev('c', true)] } } as never
    expect(placeholders(snap)).toBe(2)
    expect(placeholders({ recent_events: [ev('b')] } as never)).toBe(0)
  })
})
