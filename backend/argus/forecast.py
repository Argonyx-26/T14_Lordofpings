"""Where an incident is heading, and what each response would do (Endsley's level 3 situation awareness: projection).

Nothing here is a guess dressed up as a number. Every projected score is the real scorer (fusion/score.py) run on
the incident's real evidence plus one hypothetical signal, at the strength that signal type actually has (the
median of what ARGUS has seen today, or the rule's own emit() value from playbook `typical`). The pieces:

- script      the crime script the incident follows (playbook `scripts`: precursor -> commission -> departure),
              the stage it has reached, and the stages still ahead with the action that disrupts each one
- whatifs     "what would change this score": the next stages, another sensor agreeing, night time, the other
              security profiles, a dismissal, and the evidence window closing
- responses   a course-of-action comparison: for each candidate action, who carries it out, how long until it
              takes effect (walking distance from the nearest guard post, or the site's stated service times),
              which stage it disrupts, how many people it touches (phones in the area right now), how disruptive
              it is, and the decision it records. Ranked by a stated rule, never by a model.

Assumptions (guard posts, walking speed, police and medical times) live in site.yaml `response` and are returned
with the forecast so the console can show them as assumptions.
"""
import math
import statistics
from datetime import datetime, timezone

from argus.config import SiteConfig, profiles, site
from argus.fusion.engine import FusionEngine, decisive_signal, headline
from argus.fusion.score import score_incident
from argus.schema import Event, Incident

CRIT_MARGIN = 20        # Critical = open threshold + 20 (same bands as the console)
SOURCES = ("cctv", "door", "device")
CORROBORATING = {"door": "door_surge", "device": "device_crowding", "cctv": "loitering"}


def source_of(signal_type: str) -> str:
    if signal_type.startswith("device_"):
        return "device"
    if signal_type.startswith("door_"):
        return "door"
    return "cctv"


def level(score: float, cfg: SiteConfig) -> str:
    f = cfg.fusion
    if score >= f["open_threshold"] + CRIT_MARGIN:
        return "critical"
    if score >= f["open_threshold"]:
        return "high"
    if score >= f["watch_threshold"]:
        return "watch"
    return "low"


def typical_strength(signal_type: str, log: list[Event], cfg: SiteConfig) -> tuple[float, float, str]:
    """(severity, confidence, basis) for a signal of this type: the median of today's, else the rule's own value."""
    seen = [e for e in log if e.type == signal_type and e.severity >= cfg.fusion["context_max_severity"]]
    if len(seen) >= 3:
        return (round(statistics.median(e.severity for e in seen), 3), round(statistics.median(e.confidence for e in seen), 3),
                f"median of {len(seen)} seen today")
    t = cfg.playbook.get("typical", {}).get(signal_type, {"severity": 0.4, "confidence": 0.6})
    return t["severity"], t["confidence"], "the detector's usual strength"


class _Scorer:
    """Re-scores an incident's evidence the way the engine does, under a given config."""

    def __init__(self, cfg: SiteConfig, feedback: float, damping: float):
        self.cfg, self.feedback, self.damping = cfg, feedback, damping
        self._engine = FusionEngine(cfg)

    def adjust(self, ev: Event) -> Event | None:
        """The profile's view of a raw signal; None when it would only be routine context."""
        ev = self._engine._apply_profile(ev)
        return ev if ev.severity >= self.cfg.fusion["context_max_severity"] else None

    def run(self, signals: list[Event], area: str, t: float, feedback: float | None = None) -> dict:
        b = score_incident(signals, area, t, self.cfg, self.feedback if feedback is None else feedback, self.damping)
        types = list(dict.fromkeys(e.type for e in signals))
        f = self.cfg.fusion
        opens = b.score >= f["open_threshold"] or decisive_signal(signals, self.cfg) is not None
        return {"score": b.score, "level": level(b.score, self.cfg), "opens": opens,
                "watch": not opens and b.score >= f["watch_threshold"],
                "title": headline(types, signals, self.cfg) if signals else "", "breakdown": b.model_dump()}


def _raw(e: Event) -> Event:
    """The signal as the detector emitted it, before any profile weighting."""
    raw = e.attrs.get("raw_severity")
    return e if raw is None else e.model_copy(update={"severity": raw})


def _hypothetical(signal_type: str, inc: Incident, t: float, log: list[Event], cfg: SiteConfig) -> tuple[Event, str]:
    sev, conf, basis = typical_strength(signal_type, log, cfg)
    return Event(event_id=f"whatif-{signal_type}", t=t, source=source_of(signal_type), sensor_id="whatif",
                 zone=inc.zones[0] if inc.zones else inc.area, area=inc.area, type=signal_type, severity=sev,
                 confidence=conf, provenance="computed", attrs={"hypothetical": True}), basis


def match_script(signal_types: list[str], cfg: SiteConfig) -> dict | None:
    """The script whose stages the incident has progressed furthest along (ties: more stages matched)."""
    best, key = None, (-1, -1)
    for sid, s in (cfg.playbook.get("scripts") or {}).items():
        reached = [i for i, st in enumerate(s["stages"]) if set(st["types"]) & set(signal_types)]
        if not reached:
            continue
        k = (max(reached), len(reached))
        if k > key:
            best, key = {"id": sid, **s, "reached": reached}, k
    return best


def people_in_area(area: str, log: list[Event], now: float) -> int | None:
    """Phones in the area right now, from the GPS enter/exit stream (None when there is no GPS for it)."""
    where: dict[str, str | None] = {}
    seen_gps = False
    for e in log:
        if e.t > now or e.source != "device" or not e.entity:
            continue
        seen_gps = True
        if e.type == "device_enter":
            where[e.entity.id] = e.area
        elif e.type in ("device_exit", "device_fast_exit"):
            where[e.entity.id] = e.attrs.get("to") if e.attrs.get("to") not in (None, "outside") else None
    if not seen_gps:
        return None
    return sum(1 for a in where.values() if a == area)


def _metres(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat = math.radians((a[0] + b[0]) / 2)
    return math.hypot((a[0] - b[0]) * 110574, (a[1] - b[1]) * 111320 * math.cos(lat))


def _area_centre(area: str, cfg: SiteConfig) -> tuple[float, float] | None:
    shape = cfg.area_shapes.get(area)
    if shape is None:
        return None
    c = shape.context.centroid
    return (c.y, c.x)


def response_time(responder: str, area: str, cfg: SiteConfig) -> tuple[int | None, str]:
    r = cfg.raw.get("response", {})
    if responder == "camera":
        return 0, "on screen now"
    if responder == "police":
        return r.get("police_eta_s"), "typical police priority response (assumed)"
    if responder == "medical":
        return r.get("medical_eta_s"), "typical first-aid / ambulance response (assumed)"
    if responder == "staff":
        return r.get("staff_eta_s"), "site staff on the floor (assumed)"
    centre = _area_centre(area, cfg)
    posts = r.get("guard_posts") or []
    if centre is None or not posts:
        return None, "site layout unknown"
    post = min(posts, key=lambda p: _metres(tuple(p["pos"]), centre))
    d = _metres(tuple(post["pos"]), centre) * r.get("path_factor", 1.3)
    eta = r.get("dispatch_s", 30) + d / r.get("walk_mps", 1.4)
    return int(round(eta)), f"{int(round(d))} m on foot from {post['name']} (assumed post)"


def forecast(inc: Incident, evidence: list[Event], cfg: SiteConfig, now: float, *, log: list[Event] | None = None,
             feedback: float = 1.0) -> dict:
    """Everything the console's "What happens next" shows for one incident."""
    log = log or evidence
    f = cfg.fusion
    damping = f["burst"]["damping"] if inc.common_cause else 1.0
    scorer = _Scorer(cfg, feedback, damping)
    base = scorer.run(evidence, inc.area, inc.updated_at)
    types = list(dict.fromkeys(e.type for e in evidence))
    first_seen = {}
    for e in evidence:
        first_seen.setdefault(e.type, e.t)

    closes_at = inc.updated_at + f["window_s"]
    window = {"closes_at": closes_at, "remaining_s": max(0, int(closes_at - now)), "window_s": f["window_s"]}

    # -- the script and where the incident is on it
    script = match_script(types, cfg)
    script_out, ahead = None, []
    if script:
        furthest = max(script["reached"])
        stages = []
        for i, st in enumerate(script["stages"]):
            hit = [first_seen[t] for t in st["types"] if t in first_seen]
            stages.append({"id": st["id"], "label": st["label"], "types": st["types"], "action": st["action"],
                           "action_label": cfg.playbook["actions"].get(st["action"], st["action"]),
                           "reached": i in script["reached"], "at": min(hit) if hit else None,
                           "state": "done" if i in script["reached"] else ("next" if i == furthest + 1 else
                                                                           "later" if i > furthest else "skipped")})
        ahead = [s for s in stages if s["state"] in ("next", "later")]
        script_out = {"id": script["id"], "name": script["name"], "stages": stages, "furthest": furthest}

    # -- what would change this score
    whatifs: list[dict] = []

    def add(kind, label, result, detail, basis=None, signal=None):
        whatifs.append({"kind": kind, "label": label, "detail": detail, "basis": basis, "signal": signal,
                        "delta": result["score"] - base["score"], **{k: result[k] for k in ("score", "level", "opens", "watch", "title")},
                        "title_changes": bool(result["title"]) and result["title"] != base["title"]})

    for st in ahead[:3]:
        options = []
        for t in st["types"]:
            hyp, basis = _hypothetical(t, inc, now, log, cfg)
            adj = scorer.adjust(hyp)
            if adj is None:
                continue
            options.append((scorer.run(evidence + [adj], inc.area, now), t, basis))
        if options:
            res, t, basis = max(options, key=lambda o: o[0]["score"])
            add("next_stage", f"If {st['label'][0].lower() + st['label'][1:]}", res,
                f"{cfg.playbook['titles'].get(t, t)} at usual strength joins this incident", basis, t)

    for src in SOURCES:
        if src in inc.sources or not any(e.source == src and e.area == inc.area for e in log):
            continue       # already agreeing, or no such sensor covers this area
        t = CORROBORATING[src]
        hyp, basis = _hypothetical(t, inc, now, log, cfg)
        adj = scorer.adjust(hyp)
        if adj is not None:
            label = {"door": "If the door sensors agree", "device": "If people's phones agree", "cctv": "If a camera agrees"}[src]
            add("corroborate", label, scorer.run(evidence + [adj], inc.area, now),
                f"{cfg.playbook['titles'].get(t, t)}: a second, independent source raises the corroboration factor", basis, t)

    if time_night := f.get("night"):
        local_hour = (datetime.fromtimestamp(inc.updated_at, timezone.utc) + cfg.utc_offset).hour
        is_night = local_hour >= time_night["start_hour"] or local_hour < time_night["end_hour"]
        if not is_night:
            night_t = inc.updated_at + ((23 - local_hour) % 24) * 3600
            add("night", "If this happened at night", scorer.run(evidence, inc.area, night_t),
                f"night hours weigh ×{time_night['factor']}")

    raw = [_raw(e) for e in evidence]
    for pid, p in profiles()["profiles"].items():
        if pid == cfg.profile:
            continue
        pcfg = site().with_profile(pid)
        ps = _Scorer(pcfg, feedback, damping)
        adjusted = [a for a in (ps.adjust(e) for e in raw) if a is not None]
        if not adjusted:
            add("profile", f"Under the {p['label']} profile", {"score": 0, "level": "low", "opens": False, "watch": False, "title": ""},
                "every signal here would be routine context")
            continue
        add("profile", f"Under the {p['label']} profile", ps.run(adjusted, inc.area, inc.updated_at),
            f"opens at {pcfg.fusion['open_threshold']}, watch at {pcfg.fusion['watch_threshold']}")

    penalty = f["dismiss_penalty"]
    add("dismiss", "If similar alerts here were dismissed", scorer.run(evidence, inc.area, inc.updated_at, feedback * penalty),
        f"each dismissal multiplies this area's score for these signals by ×{penalty}")

    # -- course-of-action comparison
    meta = cfg.playbook.get("action_meta", {})
    candidates: list[str] = []
    for a in ([inc.brief.action_id] if inc.brief else []) + [s["action"] for s in ahead[:2]] + \
             ([s["action"] for s in script_out["stages"] if s["reached"]][-1:] if script_out else []) + \
             ["dispatch_guard", "notify_police", "review_footage"]:
        if a in cfg.playbook["actions"] and a in meta and a not in candidates:
            candidates.append(a)
    people = people_in_area(inc.area, log, now)
    next_stage = ahead[0] if ahead else None
    reached_now = [s for s in script_out["stages"] if s["reached"]][-1] if script_out else None
    responses = []
    for a in candidates:
        m = meta[a]
        eta, eta_basis = response_time(m["responder"], inc.area, cfg)
        disrupts = next((s for s in ahead if s["action"] == a), None)
        answers = reached_now if reached_now and reached_now["action"] == a else None
        touches = people if m["disruption"] >= 2 else (1 if m["responder"] != "camera" else 0)
        in_window = eta is not None and eta <= window["remaining_s"]
        responses.append({
            "action": a, "label": cfg.playbook["actions"][a], "responder": m["responder"],
            "time_to_effect_s": eta, "eta_basis": eta_basis, "before_window_closes": in_window,
            "disrupts": disrupts["label"] if disrupts else None, "prevents_next": bool(disrupts and disrupts is next_stage),
            "answers": answers["label"] if answers else None,
            "people_affected": touches, "people_basis": "phones in the area now" if m["disruption"] >= 2 and people is not None else None,
            "disruption": m["disruption"], "records": m["records"],
            "recommended": bool(inc.brief and inc.brief.action_id == a),
        })

    # stated ranking rule: stops what comes next > answers what is happening now > anything else; then faster; then
    # less disruptive
    def rank_key(r):
        purpose = 0 if r["prevents_next"] else 1 if r["disrupts"] else 2 if r["answers"] else 3
        return (purpose, r["time_to_effect_s"] if r["time_to_effect_s"] is not None else 10 ** 6, r["disruption"])
    responses.sort(key=rank_key)
    for i, r in enumerate(responses):
        r["rank"] = i + 1
        why = []
        if r["prevents_next"]:
            why.append(f"stops the next stage ({r['disrupts'].lower()})")
        elif r["disrupts"]:
            why.append(f"disrupts a later stage ({r['disrupts'].lower()})")
        if r["answers"]:
            why.append(f"deals with what is happening now ({r['answers'].lower()})")
        if r["time_to_effect_s"] is not None:
            why.append("takes effect at once" if r["time_to_effect_s"] == 0 else
                       f"in effect in {r['time_to_effect_s'] // 60}:{r['time_to_effect_s'] % 60:02d}")
        r["why"] = "; ".join(why) or "general response"

    return {
        "incident_id": inc.incident_id, "as_of": now, "profile": cfg.profile,
        "base": {k: base[k] for k in ("score", "level", "title")},
        "thresholds": {"watch": f["watch_threshold"], "open": f["open_threshold"], "critical": f["open_threshold"] + CRIT_MARGIN},
        "window": window, "script": script_out, "whatifs": whatifs, "responses": responses,
        "context": {"people_in_area": people, "people_basis": "phones in the area now (GPS)" if people is not None else None,
                    "assumptions": cfg.raw.get("response", {})},
    }


def risk_timeline(events: list[Event], cfg: SiteConfig) -> list[dict]:
    """The highest live incident score after each signal, for an uploaded clip's risk chart."""
    engine = FusionEngine(cfg)
    points = []
    for ev in sorted(events, key=lambda e: e.t):
        changed = engine.ingest(ev)
        if not changed:
            continue
        live = [i for i in engine.incidents.values() if i.status in ("watch", "open", "ack", "escalated", "candidate")
                and ev.t - i.updated_at <= cfg.fusion["window_s"]]
        points.append({"t": ev.t, "score": max((i.score for i in live), default=0),
                       "incident_id": changed[0].incident_id, "type": ev.type})
    return points




def add_to_snapshot(path: str) -> int:
    """Attach a forecast to every incident in an exported snapshot (the console's offline `?mock` data), computed from
    the snapshot's own incidents, evidence and recent events under the site as tuned. Returns how many were added."""
    import json
    from pathlib import Path

    p = Path(path)
    snap = json.loads(p.read_text(encoding="utf-8"))
    cfg = site()
    evidence = {k: [Event(**e) for e in v] for k, v in (snap.get("evidence") or {}).items()}
    log = sorted({e.event_id: e for e in [Event(**e) for e in snap.get("recent_events", [])] +
                  [e for v in evidence.values() for e in v]}.values(), key=lambda e: e.t)
    now = snap["clock"]["sim_t"]
    out = {}
    for raw in snap["incidents"]:
        inc = Incident(**raw)
        if inc.status in ("candidate", "dismissed"):
            continue
        out[inc.incident_id] = forecast(inc, evidence.get(inc.incident_id, []), cfg, now, log=[e for e in log if e.t <= now])
    snap["forecasts"] = out
    p.write_text(json.dumps(snap, separators=(",", ":")), encoding="utf-8")
    return len(out)


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3 or sys.argv[1] != "snapshot":
        sys.exit("usage: python -m argus.forecast snapshot <path to snapshot.json>")
    print(f"forecasts added for {add_to_snapshot(sys.argv[2])} incidents")
