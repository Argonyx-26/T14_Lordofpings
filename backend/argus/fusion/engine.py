"""Streaming fusion: events in, ranked incidents out.

- Routine events (severity below the context level) are counted per area, never alerted on.
- Signals in the same area within `window_s` join one incident.
- Bursts of the same (area, source, type) are treated as one common-cause signal and damped.
- Operator dismissals lower future scores for that (area, type) pair.
The engine is deterministic: the same events in the same order give the same incidents.
"""
from collections import Counter, defaultdict, deque

from argus.config import SiteConfig
from argus.fusion.score import score_incident
from argus.schema import Event, Incident

ACTIVE = ("candidate", "watch", "open", "ack", "escalated")


class FusionEngine:
    def __init__(self, cfg: SiteConfig):
        self.cfg = cfg
        self.reset()

    def reset(self) -> None:
        self.incidents: dict[str, Incident] = {}
        self.events: dict[str, Event] = {}          # every signal kept for evidence lookup
        self._signals: dict[str, list[Event]] = defaultdict(list)
        self._active_by_area: dict[str, str] = {}
        self._bursts: dict[tuple, deque] = defaultdict(deque)
        self._feedback: dict[tuple[str, str], float] = defaultdict(lambda: 1.0)
        self._seq = 0
        self.now = 0.0
        self.counts = Counter()                     # raw, by source, routine, siloed alerts, signals
        self.routine_by_area = Counter()

    # ---- ingestion -------------------------------------------------------------------------
    def ingest(self, ev: Event) -> list[Incident]:
        f = self.cfg.fusion
        self.now = max(self.now, ev.t)
        self.counts["raw"] += 1
        self.counts[f"source:{ev.source}"] += 1
        if ev.severity >= f["siloed_alert_severity"]:
            self.counts["siloed_alerts"] += 1       # what a per-stream threshold system would page on

        if ev.severity < f["context_max_severity"]:
            self.counts["routine"] += 1
            self.routine_by_area[ev.area] += 1
            return []

        self.counts["signals"] += 1
        self.events[ev.event_id] = ev
        burst = self._is_burst(ev)

        inc = self._active_incident(ev.area, ev.t)
        if inc is None:
            inc = self._new_incident(ev)
        self._signals[inc.incident_id].append(ev)
        inc.event_ids.append(ev.event_id)
        inc.updated_at = ev.t
        if ev.zone not in inc.zones:
            inc.zones.append(ev.zone)
        if ev.type not in inc.signal_types:
            inc.signal_types.append(ev.type)
        if ev.source not in inc.sources:
            inc.sources.append(ev.source)
        inc.common_cause = inc.common_cause or burst
        inc.composed = inc.composed or bool(ev.attrs.get("composed"))
        self._rescore(inc)
        return [inc]

    def _is_burst(self, ev: Event) -> bool:
        b = self.cfg.fusion["burst"]
        q = self._bursts[(ev.area, ev.source, ev.type)]
        q.append(ev.t)
        while q and q[0] < ev.t - b["window_s"]:
            q.popleft()
        return len(q) >= b["min_count"]

    def _active_incident(self, area: str, t: float) -> Incident | None:
        iid = self._active_by_area.get(area)
        if iid is None:
            return None
        inc = self.incidents[iid]
        if inc.status not in ACTIVE or t - inc.updated_at > self.cfg.fusion["window_s"]:
            return None
        return inc

    def _new_incident(self, ev: Event) -> Incident:
        self._seq += 1
        iid = f"INC-{self._seq:04d}"
        inc = Incident(
            incident_id=iid, area=ev.area, zones=[ev.zone], status="candidate",
            first_signal_at=ev.t, updated_at=ev.t, score=0, peak_score=0,
            score_breakdown=score_incident([], ev.area, ev.t, self.cfg),
            sources=[ev.source], event_ids=[], signal_types=[ev.type], title="",
        )
        self.incidents[iid] = inc
        self._active_by_area[ev.area] = iid
        return inc

    # ---- scoring and status ----------------------------------------------------------------
    def _rescore(self, inc: Incident) -> None:
        f = self.cfg.fusion
        signals = self._signals[inc.incident_id]
        feedback = min((self._feedback[(inc.area, t)] for t in inc.signal_types), default=1.0)
        damping = f["burst"]["damping"] if inc.common_cause else 1.0
        inc.score_breakdown = score_incident(signals, inc.area, inc.updated_at, self.cfg, feedback, damping)
        inc.score = inc.score_breakdown.score
        inc.peak_score = max(inc.peak_score, inc.score)
        inc.title = self._title(inc, signals)
        if inc.status in ("candidate", "watch"):
            if inc.score >= f["open_threshold"]:
                inc.status = "open"
                inc.opened_at = inc.updated_at
                self.counts["incidents_opened"] += 1
            elif inc.score >= f["watch_threshold"]:
                inc.status = "watch"

    def _title(self, inc: Incident, signals: list[Event]) -> str:
        titles = self.cfg.playbook["titles"]
        top = max(signals, key=lambda e: e.severity)
        name = titles.get(top.type, top.type.replace("_", " ").capitalize())
        where = self.cfg.area_name(inc.area)
        extra = f" · {len(inc.sources)} sources agree" if len(inc.sources) > 1 else ""
        cause = " · likely common cause" if inc.common_cause else ""
        return f"{name} — {where}{extra}{cause}"

    # ---- operator actions ------------------------------------------------------------------
    def act(self, incident_id: str, action: str) -> Incident:
        inc = self.incidents[incident_id]
        if action == "ack":
            inc.status = "ack"
        elif action == "escalate":
            inc.status = "escalated"
        elif action == "dismiss":
            inc.status = "dismissed"
            for t in inc.signal_types:
                self._feedback[(inc.area, t)] *= self.cfg.fusion["dismiss_penalty"]
            if self._active_by_area.get(inc.area) == incident_id:
                del self._active_by_area[inc.area]
        else:
            raise ValueError(f"unknown action {action!r}")
        return inc

    # ---- views -----------------------------------------------------------------------------
    def ranked(self, include_candidates: bool = False) -> list[Incident]:
        shown = ("watch", "open", "ack", "escalated") + (("candidate",) if include_candidates else ())
        items = [i for i in self.incidents.values() if i.status in shown]
        order = {"open": 0, "escalated": 0, "ack": 1, "watch": 2, "candidate": 3}
        return sorted(items, key=lambda i: (order[i.status], -i.score, -i.updated_at))

    def evidence(self, incident_id: str) -> list[Event]:
        return list(self._signals[incident_id])

    def summary(self) -> dict:
        return {
            "raw_events": self.counts["raw"],
            "routine_events": self.counts["routine"],
            "signals": self.counts["signals"],
            "siloed_alerts": self.counts["siloed_alerts"],
            "incidents_open": sum(1 for i in self.incidents.values() if i.status in ("open", "ack", "escalated")),
            "incidents_watch": sum(1 for i in self.incidents.values() if i.status == "watch"),
            "by_source": {k.split(":", 1)[1]: v for k, v in self.counts.items() if k.startswith("source:")},
        }
