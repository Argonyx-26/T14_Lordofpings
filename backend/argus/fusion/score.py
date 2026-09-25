"""Transparent 0-100 incident score.

score = 100 * S * (0.5 + 0.5*C) * K * R * T * F, capped at 100, where
  S  combined severity: noisy-OR over the strongest signal of each *source* (one camera
     firing ten times is one piece of evidence, not ten)
  C  mean confidence of those strongest signals
  K  area criticality factor, 0.6 + 0.4 * criticality
  R  corroboration: 1.0 / 1.25 / 1.45 for 1 / 2 / 3+ independent sources above the context level
  T  time-of-day factor (night hours weigh more)
  F  operator feedback (dismissals of the same area+type damp future scores)
"""
from datetime import datetime, timezone

from argus.config import SiteConfig
from argus.schema import Event, ScoreBreakdown


def strongest_per_source(signals: list[Event]) -> dict[str, Event]:
    best: dict[str, Event] = {}
    for e in signals:
        if e.source not in best or e.severity * e.confidence > best[e.source].severity * best[e.source].confidence:
            best[e.source] = e
    return best


def time_factor(t: float, cfg: SiteConfig) -> float:
    night = cfg.fusion["night"]
    hour = (datetime.fromtimestamp(t, timezone.utc) + cfg.utc_offset).hour
    is_night = hour >= night["start_hour"] or hour < night["end_hour"]
    return night["factor"] if is_night else 1.0


def score_incident(signals: list[Event], area: str, t: float, cfg: SiteConfig,
                   feedback: float = 1.0, damping: float = 1.0) -> ScoreBreakdown:
    f = cfg.fusion
    best = strongest_per_source(signals)
    if not best:
        return ScoreBreakdown(severity=0, confidence=0, criticality=0, corroboration=1, time_factor=1, score=0)

    miss = 1.0
    for e in best.values():
        miss *= 1.0 - e.severity * damping
    severity = 1.0 - miss
    confidence = sum(e.confidence for e in best.values()) / len(best)
    criticality = 0.6 + 0.4 * cfg.criticality(area)
    n_sources = sum(1 for e in best.values() if e.severity >= f["context_max_severity"])
    factors = f["corroboration_factors"]
    corroboration = factors[min(max(n_sources, 1), len(factors)) - 1]
    tf = time_factor(t, cfg)

    raw = severity * (0.5 + 0.5 * confidence) * criticality * corroboration * tf * feedback
    return ScoreBreakdown(
        severity=round(severity, 3), confidence=round(confidence, 3), criticality=round(criticality, 3),
        corroboration=corroboration, time_factor=tf, feedback=round(feedback, 3),
        score=int(round(min(raw, 1.0) * 100)),
    )
