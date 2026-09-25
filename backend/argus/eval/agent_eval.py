"""How good is the investigator (argus/agent.py)? Scored against the MEVA annotations, which it never sees.

Two sets, both in the demo window (15 March 2018, 14:50-15:20):
  alerts     every camera bag alert (custody change, abandoned object), investigated 30 s after it fired, labelled
             like vlm_check.py: 'staged' if it is part of a staged theft or abandonment on that camera, else 'false'.
             Baseline: the vision model alone on the same alerts (data/cache/vlm_check.json).
  incidents  every incident ARGUS surfaced by 15:20, investigated at 15:20; 'staged' if a staged event on one of
             its cameras falls inside it, else 'other' (crowd surges and the like: real activity, no staged crime).
Each item runs RUNS times (the model is not deterministic). A real alert counts as KEPT unless the verdict is
false_alarm or nothing_found; a false one counts as CAUGHT when it is false_alarm.

Usage (repo root, needs GEMINI_API_KEY):  python -m argus.eval.agent_eval [--runs 2]
Writes data/cache/agent_eval.json and prints a summary.
"""
import argparse
import json
import sys
import time
from collections import Counter

from argus import settings
from argus.agent import Case, run
from argus.config import site
from argus.fusion.engine import FusionEngine
from argus.ingest import demo_window, load_all_events
from argus.ingest.groundtruth import load_ground_truth
from argus.replay.clock import Replay
from argus.vision.vlm_check import label

ALERT_TYPES = ("custody_change", "abandoned_object")
DISMISSED = ("false_alarm", "nothing_found")


def world(cfg, events, at: float):
    engine = FusionEngine(cfg)
    replay = Replay(events, engine, *demo_window(cfg))
    replay.seek(at)
    return Case(events, list(engine.incidents.values()), replay.sim_t, cfg, evidence=engine.evidence)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=2)
    args = ap.parse_args(argv)
    cfg = site()
    events = load_all_events(cfg)
    truth = load_ground_truth(settings.ANNOTATION_DIR, cfg)
    start, end = demo_window(cfg)
    rows = []

    alerts = [e for e in events if e.source == "cctv" and e.type in ALERT_TYPES and start <= e.t <= end]
    for e in alerts:
        lab = label({"sensor_id": e.sensor_id, "t": e.t}, truth)
        for k in range(args.runs):
            case = world(cfg, events, min(e.t + 30, end))
            q = (f"Investigate the camera alert {e.event_id} ({e.type.replace('_', ' ')} on camera {e.sensor_id} at "
                 f"{cfg.epoch_to_local(e.t)[11:19]}): is it real?")
            out = run(q, case)
            rows.append({"set": "alerts", "item": e.event_id, "label": lab, "run": k, "verdict": out["verdict"],
                         "confidence": out["confidence"], "steps": len(out["steps"]), "seconds": out["seconds"],
                         "looked": sum(s["tool"] == "look_at_camera" for s in out["steps"]),
                         "generated_by": out["generated_by"], "answer": out["answer"]})
            print(f"{e.event_id:<18} {lab:<7} -> {out['verdict']:<13} {out['confidence']:.2f} "
                  f"({len(out['steps'])} steps, {out['seconds']} s)", flush=True)

    final = world(cfg, events, end)
    for iid, inc in sorted(final.incidents.items()):
        cams = {e.sensor_id for e in final._evidence(iid) if e.source == "cctv"}
        staged = any(g.camera in cams and inc.first_signal_at - 60 <= g.t_start <= inc.updated_at + 60 for g in truth)
        for k in range(args.runs):
            case = world(cfg, events, end)
            out = run(f"Investigate {iid} ({inc.title.split(' — ')[0]}): is it real, and what should we do?", case)
            rows.append({"set": "incidents", "item": iid, "title": inc.title.split(" — ")[0],
                         "label": "staged" if staged else "other", "run": k, "verdict": out["verdict"],
                         "confidence": out["confidence"], "steps": len(out["steps"]), "seconds": out["seconds"],
                         "looked": sum(s["tool"] == "look_at_camera" for s in out["steps"]),
                         "generated_by": out["generated_by"], "answer": out["answer"]})
            print(f"{iid:<18} {rows[-1]['label']:<7} -> {out['verdict']:<13} {out['confidence']:.2f} "
                  f"({len(out['steps'])} steps, {out['seconds']} s)  {rows[-1]['title']}", flush=True)

    def part(s, lab):
        return [r for r in rows if r["set"] == s and r["label"] == lab and r["generated_by"] == "agent"]
    staged_a, false_a, staged_i, other_i = part("alerts", "staged"), part("alerts", "false"), \
        part("incidents", "staged"), part("incidents", "other")
    ok = [r for r in rows if r["generated_by"] == "agent"]
    try:
        vlm = json.loads((settings.CACHE_DIR / "vlm_check.json").read_text(encoding="utf-8"))["summary"]
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        vlm = None
    summary = {
        "model": ok[0]["generated_by"] and __import__("argus.agent", fromlist=["GEMINI_MODEL"]).GEMINI_MODEL if ok else None,
        "runs_per_item": args.runs, "runs": len(rows), "runs_completed_by_agent": len(ok),
        "alerts": {"staged_items": len({r["item"] for r in staged_a}), "false_items": len({r["item"] for r in false_a}),
                   "staged_kept": f"{sum(r['verdict'] not in DISMISSED for r in staged_a)}/{len(staged_a)}",
                   "staged_confirmed_or_likely": f"{sum(r['verdict'] in ('confirmed', 'likely') for r in staged_a)}/{len(staged_a)}",
                   "false_caught": f"{sum(r['verdict'] == 'false_alarm' for r in false_a)}/{len(false_a)}",
                   "verdicts_staged": dict(Counter(r["verdict"] for r in staged_a)),
                   "verdicts_false": dict(Counter(r["verdict"] for r in false_a))},
        "vision_model_alone_baseline": vlm,
        "incidents": {"staged_kept": f"{sum(r['verdict'] not in DISMISSED for r in staged_i)}/{len(staged_i)}",
                      "verdicts_staged": dict(Counter(r["verdict"] for r in staged_i)),
                      "verdicts_other": dict(Counter(r["verdict"] for r in other_i))},
        "mean_steps": round(sum(r["steps"] for r in ok) / max(len(ok), 1), 1),
        "mean_frames_looked_at": round(sum(r["looked"] for r in ok) / max(len(ok), 1), 1),
        "mean_seconds": round(sum(r["seconds"] for r in ok) / max(len(ok), 1), 1),
        "when": time.strftime("%Y-%m-%d %H:%M"),
    }
    out = settings.CACHE_DIR / "agent_eval.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
