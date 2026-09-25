// Mirrors backend/argus/schema.py — keep in sync.
export type Source = 'cctv' | 'door' | 'device' | 'auth'
export type Provenance = 'computed' | 'annotation_derived' | 'recorded'
export type Status = 'candidate' | 'watch' | 'open' | 'ack' | 'escalated' | 'dismissed'

export interface ArgusEvent {
  event_id: string
  t: number
  source: Source
  sensor_id: string
  zone: string
  area: string
  type: string
  severity: number
  confidence: number
  entity: { kind: string; id: string } | null
  provenance: Provenance
  media: { clip: string; frame: number; bbox: number[] | null } | null
  attrs: Record<string, unknown>
}

export interface ScoreBreakdown {
  severity: number
  confidence: number
  criticality: number
  corroboration: number
  time_factor: number
  feedback: number
  score: number
}

export interface Brief {
  summary: string
  why: string
  action_id: string
  evidence_ids: string[]
  generated_by: 'llm' | 'template'
  model?: string | null
}

export interface Incident {
  incident_id: string
  area: string
  zones: string[]
  status: Status
  first_signal_at: number
  opened_at: number | null
  updated_at: number
  score: number
  peak_score: number
  score_breakdown: ScoreBreakdown
  sources: Source[]
  event_ids: string[]
  signal_types: string[]
  title: string
  brief: Brief | null
  composed: boolean
  common_cause: boolean
  decisive?: boolean
}

export interface Clock {
  sim_t: number
  local: string
  playing: boolean
  speed: number
  start_t: number
  end_t: number
  finished: boolean
}

export interface Summary {
  raw_events: number
  routine_events: number
  signals: number
  siloed_alerts: number
  incidents_open: number
  incidents_watch: number
  by_source: Record<string, number>
}

export interface SiteConfigView {
  site_name: string
  areas: Record<string, { name: string; criticality: number }>
  cameras: Record<string, { zone: string; area: string; label: string; pos?: [number, number] }>
  bookmarks: { label: string; t: number }[]
  playbook: Record<string, string>
  thresholds: { watch_threshold: number; open_threshold: number; siloed_alert_severity: number; context_max_severity: number }
  window: { start_t: number; end_t: number }
  profile?: string
  profiles?: { id: string; label: string; description: string }[]
  clips: string[]
  fps: number
  attribution: string
  geometry?: Record<string, [number, number][]>
}

export interface Snapshot {
  type: 'snapshot'
  profile?: string
  clock: Clock
  summary: Summary
  incidents: Incident[]
  recent_events: ArgusEvent[]
  evidence?: Record<string, ArgusEvent[]>
  forecasts?: Record<string, Forecast>
}

export interface Tick {
  type: 'tick'
  clock: Clock
  summary: Summary
  events: ArgusEvent[]
  incidents: Incident[]
}

// Mirrors backend/argus/forecast.py
export interface ScriptStage {
  id: string
  label: string
  types: string[]
  action: string
  action_label: string
  reached: boolean
  at: number | null
  state: 'done' | 'next' | 'later' | 'skipped'
}

export interface WhatIf {
  kind: 'next_stage' | 'corroborate' | 'night' | 'profile' | 'dismiss'
  label: string
  detail: string
  basis: string | null
  signal: string | null
  score: number
  level: 'critical' | 'high' | 'watch' | 'low'
  opens: boolean
  watch: boolean
  title: string
  title_changes: boolean
  delta: number
}

export interface ResponseOption {
  action: string
  label: string
  responder: 'camera' | 'guard' | 'staff' | 'police' | 'medical'
  time_to_effect_s: number | null
  eta_basis: string
  before_window_closes: boolean
  disrupts: string | null
  prevents_next: boolean
  answers: string | null
  people_affected: number | null
  people_basis: string | null
  disruption: number
  records: 'ack' | 'escalate'
  recommended: boolean
  rank: number
  why: string
}

export interface Forecast {
  incident_id: string
  as_of: number
  profile: string | null
  base: { score: number; level: string; title: string }
  thresholds: { watch: number; open: number; critical: number }
  window: { closes_at: number; remaining_s: number; window_s: number }
  script: { id: string; name: string; stages: ScriptStage[]; furthest: number } | null
  whatifs: WhatIf[]
  responses: ResponseOption[]
  context: { people_in_area: number | null; people_basis: string | null; assumptions: Record<string, unknown> }
}
