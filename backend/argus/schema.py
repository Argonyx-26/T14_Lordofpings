"""The shared contract. Every stream writes Events; the fusion engine produces Incidents.

Keep this in sync with docs/HANDOFF_ARGUS_WINDOWS.md section 8 and frontend/src/types.ts.
"""
from typing import Literal

from pydantic import BaseModel, Field

Source = Literal["cctv", "door", "device", "auth"]
Provenance = Literal["computed", "annotation_derived", "recorded"]
IncidentStatus = Literal["candidate", "watch", "open", "ack", "escalated", "dismissed"]


class Entity(BaseModel):
    kind: Literal["track", "device", "door", "user", "area"]
    id: str


class Media(BaseModel):
    clip: str
    frame: int
    bbox: list[float] | None = None


class Event(BaseModel):
    event_id: str
    t: float = Field(description="UTC epoch seconds")
    source: Source
    sensor_id: str
    zone: str
    area: str = Field("", description="Coarse area used for fusion; filled from site config when empty")
    type: str
    severity: float = Field(0.0, ge=0.0, le=1.0)
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    entity: Entity | None = None
    provenance: Provenance
    media: Media | None = None
    attrs: dict = Field(default_factory=dict)


class ScoreBreakdown(BaseModel):
    severity: float
    confidence: float
    criticality: float
    corroboration: float
    time_factor: float
    feedback: float = 1.0
    score: int


class Brief(BaseModel):
    summary: str
    why: str
    action_id: str
    evidence_ids: list[str]
    generated_by: Literal["llm", "template"]
    model: str | None = None   # which LLM wrote it (None for the template)


class Incident(BaseModel):
    incident_id: str
    area: str
    zones: list[str]
    status: IncidentStatus
    first_signal_at: float
    opened_at: float | None = None
    updated_at: float
    score: int
    peak_score: int
    score_breakdown: ScoreBreakdown
    sources: list[Source]
    event_ids: list[str]
    signal_types: list[str]
    title: str
    brief: Brief | None = None
    composed: bool = Field(False, description="True if any evidence relies on a cross-dataset mapping we created")
    common_cause: bool = False
