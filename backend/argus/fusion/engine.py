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


def headline(signal_types: list[str], signals: list[Event], cfg: SiteConfig) -> str:
    """What happened, in operator words. A known story (playbook `stories`, all its types present) beats the
    single strongest signal: an unattended bag that is then carried off is a possible theft, not "an unattended
    object"."""
    for story in cfg.playbook.get("stories", []):
        if set(story["types"]) <= set(signal_types):
            return story["title"]
    titles = cfg.playbook["titles"]
    top = max(signals, key=lambda e: e.severity)
    return titles.get(top.type, top.type.replace("_", " ").capitalize())


def story_action(signal_types: list[str], cfg: SiteConfig) -> str | None:
    for story in cfg.playbook.get("stories", []):
        if set(story["types"]) <= set(signal_types):
            return story.get("action")
    return None


def decisive_signal(signals: list[Event], cfg: SiteConfig) -> Event | None:
    """A signal that warrants a human on its own (playbook `decisive`), whatever the score says."""
    rules = cfg.playbook.get("decisive", {})
    for e in signals:
        r = rules.get(e.type)
        if r and e.severity >= r["min_severity"] and e.confidence >= r["min_confidence"]:
            return e
    return None


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
        self.counts = Counter()                     # raw, by source, routine, siloed alerts, signals
        self.routine_by_area = Counter()

    # ---- ingestion -------------------------------------------------------------------------
    def ingest(self, ev: Event) -> list[Incident]:
        f = self.cfg.fusion
        self.counts["raw"] += 1
        self.counts[f"source:{ev.source}"] += 1
        if ev.severity >= f["siloed_alert_severity"]:
            self.counts["siloed_alerts"] += 1       # what a per-stream threshold system would page on
        ev = self._apply_profile(ev)

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

    def _apply_profile(self, ev: Event) -> Event:
        """The security profile's view of a signal (profiles.yaml `signals`): its severity weighted, or demoted to
        routine context when it lacks the profile's minimum evidence (e.g. a bag alone for less than 2 minutes in
        a park). The raw event is untouched; the adjusted copy carries the weight it got."""
        pol = self.cfg.signal_policy.get(ev.type)
        if not pol:
            return ev
        sev = min(1.0, ev.severity * pol.get("weight", 1.0))
        need = pol.get("min_unattended_s")
        if need is not None and ev.attrs.get("unattended_s", need) < need:
            sev = min(sev, self.cfg.fusion["context_max_severity"] * 0.99)
        if sev == ev.severity:
            return ev
        return ev.model_copy(update={"severity": round(sev, 3),
                                     "attrs": {**ev.attrs, "profile": self.cfg.profile, "raw_severity": ev.severity}})

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
        decisive = decisive_signal(signals, self.cfg)
        inc.decisive = decisive is not None
        if inc.status in ("candidate", "watch"):
            if inc.score >= f["open_threshold"] or decisive is not None:
                inc.status = "open"
                inc.opened_at = inc.updated_at
            elif inc.score >= f["watch_threshold"]:
                inc.status = "watch"

    def _title(self, inc: Incident, signals: list[Event]) -> str:
        name = headline(inc.signal_types, signals, self.cfg)
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
