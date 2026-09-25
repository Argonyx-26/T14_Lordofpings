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
  supervisor_pin_required?: boolean
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
  intel?: Intel
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

// Mirrors backend/argus/intel.py (patterns.py + coverage.py): the read-only layer above incidents
export interface PatternLink {
  from: string
  to: string
  kind: 'repeat' | 'near_repeat' | 'concurrent'
  script: string
  script_name: string
  from_area: string
  to_area: string
  gap_s: number
  distance_m: number | null
  walk_s: number | null
  shared_stages: string[]
  shared_types: string[]
  similarity: number
  why: string
}

export interface Series {
  series_id: string
  script: string
  script_name: string
  incidents: string[]
  areas: string[]
  start: number
  end: number
  span_s: number
  title: string
  concurrent: boolean
  reading: string
}

export interface WatchArea {
  area: string
  walk_s: number
  distance_m: number
  criticality: number
  weight: number
  cameras: string[]
  blind: boolean
  why: string
  rank: number
  heightened: boolean
}

export interface NearRepeatWatch {
  after: string
  script: string
  origin: string
  since: number
  until: number
  remaining_s: number
  areas: WatchArea[]
  site_walk_s: number
  basis: string
}

export interface AreaCoverage {
  area: string
  name: string
  criticality: number
  cameras: { id: string; label: string; recording: boolean | null }[]
  streams: Record<'cctv' | 'door' | 'device', boolean>
  installed: Record<'cctv' | 'door' | 'device', boolean>
  sees: string[]
  blind: string[]
  ceiling: { sources: number; corroboration: number | null }
  offline: string[]
  note: string
}

export interface Coverage {
  as_of: number
  behaviours: { id: string; label: string }[]
  areas: AreaCoverage[]
  visibility: number | null
  visibility_basis: string
  seen_by: Record<string, string[]>
}

export interface Intel {
  as_of: number
  links: PatternLink[]
  series: Series[]
  watch: NearRepeatWatch | null
  coverage: Coverage
}

// Supervisor-only (backend/argus/api/main.py _internals, /api/learning, /api/dismissed)
export interface Internals {
  profile: string | null
  signals: {
    event_id: string; t: number; type: string; source: Source; sensor_id: string; severity: number; raw_severity: number
    profile_weight: number | null; confidence: number; entity: { kind: string; id: string } | null
    media: { clip: string; frame: number; bbox: number[] | null } | null; attrs: Record<string, unknown>; provenance: Provenance
    counts_for_source: boolean
  }[]
  contributions: { source: Source; score_without: number; adds: number }[]
  feedback: { factor: number; from: { area: string; type: string; factor: number }[] }
  burst_damping: number
}

export interface LearnedRule {
  area: string; area_name: string; type: string; factor: number; penalty: number
  dismissals: { incident_id: string; sim_t: number; role: string }[]
}
