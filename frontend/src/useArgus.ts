import { useCallback, useEffect, useReducer, useRef } from 'react'
import mockConfig from './mock/config.json'
import mockSnapshot from './mock/snapshot.json'
import { API, MOCK, WS_URL } from './lib'
import type { ArgusEvent, Clock, Incident, SiteConfigView, Snapshot, Summary, Tick } from './types'

export interface ArgusState {
  config: SiteConfigView | null
  clock: Clock | null
  summary: Summary | null
  incidents: Record<string, Incident>
  events: ArgusEvent[]
  connected: boolean
  mock: boolean
  mockEvidence: Record<string, ArgusEvent[]>
}

type Action =
  | { kind: 'config'; config: SiteConfigView }
  | { kind: 'snapshot'; snap: Snapshot }
  | { kind: 'tick'; tick: Tick }
  | { kind: 'connected'; value: boolean }

const MAX_EVENTS = 400

function reducer(s: ArgusState, a: Action): ArgusState {
  switch (a.kind) {
    case 'config':
      return { ...s, config: a.config }
    case 'connected':
      return { ...s, connected: a.value }
    case 'snapshot':
      return {
        ...s,
        clock: a.snap.clock,
        summary: a.snap.summary,
        incidents: Object.fromEntries(a.snap.incidents.map((i) => [i.incident_id, i])),
        events: a.snap.recent_events.slice(-MAX_EVENTS),
        mockEvidence: a.snap.evidence ?? s.mockEvidence,
      }
    case 'tick': {
      const incidents = { ...s.incidents }
      for (const i of a.tick.incidents) incidents[i.incident_id] = i
      const events = a.tick.events.length ? [...s.events, ...a.tick.events].slice(-MAX_EVENTS) : s.events
      return { ...s, clock: a.tick.clock, summary: a.tick.summary, incidents, events }
    }
  }
}

const initial: ArgusState = {
  config: null, clock: null, summary: null, incidents: {}, events: [], connected: false, mock: MOCK, mockEvidence: {},
}

export function useArgus() {
  const [state, dispatch] = useReducer(reducer, initial)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (MOCK) {
      dispatch({ kind: 'config', config: mockConfig as SiteConfigView })
      dispatch({ kind: 'snapshot', snap: mockSnapshot as unknown as Snapshot })
      return
    }
    let cancelled = false
    let retry: ReturnType<typeof setTimeout>

    const loadConfig = () =>
      fetch(API + '/api/config')
        .then((r) => r.json())
        .then((config) => !cancelled && dispatch({ kind: 'config', config }))
        .catch(() => { if (!cancelled) retry = setTimeout(loadConfig, 2000) })

    const connect = () => {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws
      ws.onopen = () => dispatch({ kind: 'connected', value: true })
      ws.onmessage = (m) => {
        const msg = JSON.parse(m.data)
        if (msg.type === 'snapshot') dispatch({ kind: 'snapshot', snap: msg })
        else if (msg.type === 'tick') dispatch({ kind: 'tick', tick: msg })
      }
      ws.onclose = () => {
        dispatch({ kind: 'connected', value: false })
        if (!cancelled) retry = setTimeout(connect, 1500)
      }
    }
    loadConfig()
    connect()
    return () => {
      cancelled = true
      clearTimeout(retry)
      wsRef.current?.close()
    }
  }, [])

  const evidenceFor = useCallback(
    async (id: string): Promise<ArgusEvent[]> => {
      if (MOCK) return state.mockEvidence[id] ?? []
      const r = await fetch(`${API}/api/incidents/${id}`)
      return r.ok ? (await r.json()).evidence : []
    },
    [state.mockEvidence],
  )

  return { state, evidenceFor }
}
