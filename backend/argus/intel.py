"""The intel layer above incidents, in one call: pattern links, series, near-repeat watch and coverage.

Read-only: it is recomputed from the fusion engine's incidents and the event log up to the replay clock, and never
changes a score, opens or hides an incident.
"""
from argus.config import SiteConfig
from argus.coverage import coverage
from argus.patterns import intel_patterns
from argus.schema import Event, Incident


def build_intel(incidents: list[Incident], evidence_of, cfg: SiteConfig, now: float, log: list[Event],
                live: bool = False) -> dict:
    cov = coverage(cfg, log, now, live=live)
    pats = intel_patterns(incidents, evidence_of, cfg, now, cov["seen_by"])
    return {"as_of": now, **pats, "coverage": cov}


def add_to_snapshot(path: str) -> dict:
    """Attach the intel layer to an exported snapshot (the console's offline `?mock` data), from the snapshot's own
    incidents, evidence and recent events."""
    import json
    from pathlib import Path

    from argus.config import site
    p = Path(path)
    snap = json.loads(p.read_text(encoding="utf-8"))
    evidence = {k: [Event(**e) for e in v] for k, v in (snap.get("evidence") or {}).items()}
    log = [Event(**e) for e in snap.get("recent_events", [])] + [e for v in evidence.values() for e in v]
    now = snap["clock"]["sim_t"]
    incidents = [Incident(**i) for i in snap["incidents"]]
    snap["intel"] = build_intel(incidents, lambda iid: evidence.get(iid, []), site(), now, [e for e in log if e.t <= now])
    p.write_text(json.dumps(snap, separators=(",", ":")), encoding="utf-8")
    return snap["intel"]


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3 or sys.argv[1] != "snapshot":
        sys.exit("usage: python -m argus.intel snapshot <path to snapshot.json>")
    out = add_to_snapshot(sys.argv[2])
    print(f"intel added: {len(out['links'])} links, {len(out['series'])} series, "
          f"watch {'on' if out['watch'] else 'off'}, visibility {out['coverage']['visibility']}%")
