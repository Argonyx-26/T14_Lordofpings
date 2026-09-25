"""Measure ARGUS against MEVA ground truth for the demo window.

Run from backend/:  python -m argus.eval.evaluate
Writes data/cache/metrics.json (the console's metrics strip reads it).

1. Door detection   video `door_activity` events vs annotated door opens, per camera (±2 s)
2. Incident recall  staged thefts / abandoned package: did an incident cover them, and at what rank?
3. Reduction        raw events -> siloed per-stream alerts -> ARGUS incidents
4. Latency          ground-truth start -> incident opened
"""
import json
import sys

from argus import settings
from argus.config import site
from argus.fusion.engine import FusionEngine
from argus.ingest import demo_window, load_all_events
from argus.ingest.groundtruth import load_door_truth, load_ground_truth
from argus.replay.clock import Replay

DOOR_TOL_S = 2.0
GT_SLACK_S = 60.0


def door_metrics(events, truth: dict[str, list[float]]) -> dict:
    detected: dict[str, list[float]] = {}
    for e in events:
        if e.source == "cctv" and e.type == "door_activity":
            detected.setdefault(e.sensor_id, []).append(e.t)
    if not detected:
        return {"status": "pending: no cctv door_activity events yet"}
    per_cam, tp_all, fp_all, fn_all = {}, 0, 0, 0
    for cam, gt_times in truth.items():
        dets = sorted(detected.get(cam, []))
        used = [False] * len(dets)
        tp = 0
        for g in gt_times:
            best, best_d = None, DOOR_TOL_S
            for i, d in enumerate(dets):
                if not used[i] and abs(d - g) <= best_d:
                    best, best_d = i, abs(d - g)
            if best is not None:
                used[best] = True
                tp += 1
        fp, fn = used.count(False), len(gt_times) - tp
        per_cam[cam] = {"truth": len(gt_times), "detected": len(dets), "tp": tp,
                        "precision": round(tp / len(dets), 3) if dets else None,
                        "recall": round(tp / len(gt_times), 3) if gt_times else None}
        tp_all, fp_all, fn_all = tp_all + tp, fp_all + fp, fn_all + fn
    return {"status": "ok", "tolerance_s": DOOR_TOL_S, "per_camera": per_cam,
            "precision": round(tp_all / (tp_all + fp_all), 3) if tp_all + fp_all else None,
            "recall": round(tp_all / (tp_all + fn_all), 3) if tp_all + fn_all else None}


def run() -> dict:
    cfg = site()
    events = load_all_events(cfg)
    start, end = demo_window(cfg)
    engine = FusionEngine(cfg)
    Replay(events, engine, start, end).run_all()
    f = cfg.fusion

    shown = [i for i in engine.incidents.values() if i.peak_score >= f["watch_threshold"]]
    ranked = sorted(shown, key=lambda i: -i.peak_score)
    gt_rows = []
    for g in load_ground_truth(settings.ANNOTATION_DIR, cfg):
        hits = [i for i in engine.incidents.values()
                if i.area == g.area and i.first_signal_at <= g.t_end + GT_SLACK_S
                and i.updated_at >= g.t_start - GT_SLACK_S]
        best = max(hits, key=lambda i: i.peak_score, default=None)
        level = ("alerted" if best and best.peak_score >= f["open_threshold"]
                 else "watch" if best and best.peak_score >= f["watch_threshold"] else "missed")
        gt_rows.append({
            "kind": g.kind, "camera": g.camera, "area": g.area, "time": cfg.epoch_to_local(g.t_start)[11:],
            "result": level, "incident": best.incident_id if best else None,
            "peak_score": best.peak_score if best else 0,
            "rank": ranked.index(best) + 1 if best in ranked else None,
            "latency_s": round(best.opened_at - g.t_start, 1) if best and best.opened_at else None,
            "sources": best.sources if best else [],
        })

    s = engine.summary()
    raw, silo = s["raw_events"], s["siloed_alerts"]
    surfaced = s["incidents_open"] + s["incidents_watch"]
    return {
        "window": [cfg.epoch_to_local(start), cfg.epoch_to_local(end)],
        "reduction": {
            "raw_events": raw, "siloed_alerts": silo, "incidents_open": s["incidents_open"],
            "incidents_watch": s["incidents_watch"],
            "reduction_vs_raw_pct": round(100 * (1 - surfaced / raw), 1) if raw else None,
            "reduction_vs_siloed_pct": round(100 * (1 - surfaced / silo), 1) if silo else None,
        },
        "by_source": s["by_source"],
        "ground_truth": gt_rows,
        "ground_truth_alerted": sum(r["result"] == "alerted" for r in gt_rows),
        "ground_truth_total": len(gt_rows),
        "door_detection": door_metrics(events, load_door_truth(settings.ANNOTATION_DIR, cfg)),
        "cctv_events": s["by_source"].get("cctv", 0),
    }


def main() -> int:
    m = run()
    settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (settings.CACHE_DIR / "metrics.json").write_text(json.dumps(m, indent=2), encoding="utf-8")
    r = m["reduction"]
    print(f"Window {m['window'][0]} -> {m['window'][1][11:]}   events by source: {m['by_source']}")
    print(f"Raw events {r['raw_events']}  ->  siloed alerts {r['siloed_alerts']}  ->  "
          f"ARGUS incidents {r['incidents_open']} open + {r['incidents_watch']} watch")
    print(f"Ground truth alerted: {m['ground_truth_alerted']}/{m['ground_truth_total']}")
    for g in m["ground_truth"]:
        print(f"  {g['time']} {g['kind']:<18} {g['camera']} {g['area']:<12} {g['result']:<8} "
              f"score {g['peak_score']:>3} rank {g['rank']} latency {g['latency_s']} sources {g['sources']}")
    print(f"Door detection: {m['door_detection']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
