"""Export the console's offline demo (`?mock`, the hosted console) from the real replay, in one command.

    python -m argus.export_snapshot                 # the end of the window (15:20) -> frontend/src/mock/snapshot.json
    python -m argus.export_snapshot --at 14:58:00   # another moment of the replay

It replays the window exactly as the backend does, then writes what the console needs without a backend: the
snapshot (incidents, summary, recent events), every incident's evidence, forecasts and the intel layer (pattern
links, near-repeat watch, coverage). Briefs come from the LLM cache when present, else the template. Run it where the
vision events exist (data/events/cctv.jsonl, the demo laptop): elsewhere the export has no camera incidents, and it
refuses to overwrite a snapshot that has more camera evidence than the new one unless --force.
"""
import argparse
import json
from pathlib import Path

from argus import settings
from argus.brief.llm import brief_for
from argus.config import profiles, site
from argus.forecast import forecast
from argus.fusion.engine import FusionEngine
from argus.ingest import demo_window, load_all_events
from argus.intel import build_intel
from argus.replay.clock import Replay

OUT = settings.REPO_ROOT / "frontend" / "src" / "mock" / "snapshot.json"


def export(at: str | None = None, profile: str | None = None) -> dict:
    import os
    profile = profile or os.environ.get("ARGUS_PROFILE") or profiles().get("default")
    cfg = site().with_profile(profile)
    events = load_all_events(cfg)
    start, end = demo_window(cfg)
    engine = FusionEngine(cfg)
    replay = Replay(events, engine, start, end)
    now = end if at is None else cfg.local_to_epoch(f"{cfg.epoch_to_local(start)[:10]} {at}")
    replay.seek(now)
    now = replay.sim_t
    for inc in engine.incidents.values():
        if inc.status in ("open", "ack", "escalated"):
            inc.brief = brief_for(inc, engine.evidence(inc.incident_id), cfg)
    log = [e for e in events if e.t <= now]
    incidents = engine.ranked(include_candidates=True)
    feedback = lambda inc: min((engine._feedback[(inc.area, t)] for t in inc.signal_types), default=1.0)
    return {
        "type": "snapshot", "profile": profile,
        "clock": {"sim_t": now, "local": cfg.epoch_to_local(now), "playing": False, "speed": 10, "start_t": start,
                  "end_t": end, "finished": now >= end},
        "summary": engine.summary(),
        "incidents": [i.model_dump() for i in incidents],
        "recent_events": [e.model_dump() for e in log[-200:]],
        "evidence": {i.incident_id: [e.model_dump() for e in engine.evidence(i.incident_id)] for i in incidents},
        "forecasts": {i.incident_id: forecast(i, engine.evidence(i.incident_id), cfg, now, log=log, feedback=feedback(i))
                      for i in incidents if i.status not in ("candidate", "dismissed")},
        "intel": build_intel(list(engine.incidents.values()), engine.evidence, cfg, now, log),
    }


def _camera_evidence(snap: dict) -> int:
    return sum(1 for v in (snap.get("evidence") or {}).values() for e in v if e.get("source") == "cctv")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--at", help="local time of day to export, e.g. 14:58:00 (default: end of the window)")
    ap.add_argument("--profile")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--force", action="store_true", help="overwrite even if the current snapshot has more camera evidence")
    a = ap.parse_args()
    snap = export(a.at, a.profile)
    out = Path(a.out)
    if out.exists() and not a.force:
        old = json.loads(out.read_text(encoding="utf-8"))
        if _camera_evidence(old) > _camera_evidence(snap):
            raise SystemExit(f"not overwriting {out}: it has {_camera_evidence(old)} camera signals, this export "
                             f"{_camera_evidence(snap)} (no data/events/cctv.jsonl here?). --force to overwrite.")
    out.write_text(json.dumps(snap, separators=(",", ":")), encoding="utf-8")
    intel = snap["intel"]
    print(f"{out}: {snap['clock']['local']}, {len(snap['incidents'])} incidents "
          f"({sum(i['status'] in ('open', 'ack', 'escalated') for i in snap['incidents'])} open), "
          f"{_camera_evidence(snap)} camera signals, {len(intel['links'])} links, {len(intel['series'])} series, "
          f"visibility {intel['coverage']['visibility']}%")


if __name__ == "__main__":
    main()
