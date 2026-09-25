"""Measure the intel layer (argus/patterns.py) against MEVA ground truth, which it never reads.

Run from backend/:  python -m argus.eval.patterns_eval        -> data/cache/patterns_eval.json

1. Near-repeat watch   for every staged theft / abandonment after the first: one second before it started, was
                       its area among the areas the watch ranked highest ("watch next")? Chance is the share of the
                       site's areas that are marked, stated alongside.
2. Pattern links       at the end of the window: which staged incidents ended up in one series, and how many
                       incidents in a series match no staged incident (links to noise).

n is small (the demo window has 5 staged events). The numbers are reported as counts with the chance level, not
as rates.
"""
import json

from argus import settings
from argus.config import profiles, site
from argus.fusion.engine import FusionEngine
from argus.ingest import demo_window, load_all_events
from argus.ingest.groundtruth import load_ground_truth
from argus.intel import build_intel
from argus.replay.clock import Replay

SLACK_S = 60.0


def _at(events, cfg, t):
    engine = FusionEngine(cfg)
    start, end = demo_window(cfg)
    replay = Replay(events, engine, start, end)
    replay.seek(t)
    log = [e for e in events if e.t <= replay.sim_t]
    return engine, build_intel(list(engine.incidents.values()), engine.evidence, cfg, replay.sim_t, log)


def _match(g, engine) -> str | None:
    """The incident that covers a staged event: same area, evidence inside its time span (± slack)."""
    for inc in engine.incidents.values():
        if inc.area == g.area and any(g.t_start - SLACK_S <= e.t <= g.t_end + SLACK_S for e in engine.evidence(inc.incident_id)):
            return inc.incident_id
    return None


def evaluate(profile: str | None = None) -> dict:
    import os
    profile = profile or os.environ.get("ARGUS_PROFILE") or profiles().get("default")
    cfg = site().with_profile(profile)
    events = load_all_events(cfg)
    truth = load_ground_truth(settings.ANNOTATION_DIR, cfg)
    start, end = demo_window(cfg)
    truth = [g for g in truth if start <= g.t_start <= end]

    watch_rows = []
    for g in truth[1:]:
        _, intel = _at(events, cfg, g.t_start - 1)
        w = intel["watch"]
        row = {"kind": g.kind, "camera": g.camera, "area": g.area, "time": cfg.epoch_to_local(g.t_start)}
        if w is None:
            row.update(watch=None, heightened=False, rank=None, chance=None)
        else:
            a = next((x for x in w["areas"] if x["area"] == g.area), None)
            row.update(watch=w["after"], heightened=bool(a and a["heightened"]), rank=a["rank"] if a else None,
                       chance=round(sum(x["heightened"] for x in w["areas"]) / len(w["areas"]), 2))
        watch_rows.append(row)

    engine, intel = _at(events, cfg, end)
    gt_inc = {i: _match(g, engine) for i, g in enumerate(truth)}
    in_series = {iid for s in intel["series"] for iid in s["incidents"]}
    staged = {v for v in gt_inc.values() if v}
    series_rows = [{"series": s["series_id"], "title": s["title"], "incidents": s["incidents"],
                    "staged": [iid for iid in s["incidents"] if iid in staged],
                    "unmatched": [iid for iid in s["incidents"] if iid not in staged]} for s in intel["series"]]
    out = {
        "profile": profile, "window": [cfg.epoch_to_local(start), cfg.epoch_to_local(end)], "n_staged": len(truth),
        "watch": {"rows": watch_rows, "scored": sum(r["watch"] is not None for r in watch_rows),
                  "in_watch_next": sum(r["heightened"] for r in watch_rows),
                  "chance": [r["chance"] for r in watch_rows if r["chance"] is not None]},
        "links": {"series": series_rows, "links": intel["links"],
                  "staged_linked": sorted(i for i, v in gt_inc.items() if v in in_series),
                  "staged_with_incident": sorted(i for i, v in gt_inc.items() if v),
                  "unmatched_in_series": sorted({u for r in series_rows for u in r["unmatched"]})},
    }
    return out


def main() -> None:
    out = evaluate()
    path = settings.CACHE_DIR / "patterns_eval.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1), encoding="utf-8")
    w, lk = out["watch"], out["links"]
    print(f"Near-repeat watch: {w['in_watch_next']}/{w['scored']} later staged events were in a 'watch next' area "
          f"one second before they began (chance per event: {w['chance']})")
    for r in w["rows"]:
        print(f"  {r['time'][11:]} {r['kind']:<18} {r['area']:<12} watch after {r['watch']}: "
              f"{'WATCH NEXT' if r['heightened'] else 'not marked'} (rank {r['rank']})")
    print(f"Pattern links: {len(lk['staged_linked'])} of {len(lk['staged_with_incident'])} staged events with an incident "
          f"sit in a series; incidents in a series matching no staged event: {len(lk['unmatched_in_series'])} {lk['unmatched_in_series']}")
    for s in lk["series"]:
        print(f"  {s['series']}: {s['title']} · staged {s['staged']} · unmatched {s['unmatched']}")
    print(f"-> {path}")


if __name__ == "__main__":
    main()
