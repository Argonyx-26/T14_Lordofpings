"""Door-sensor experiments: re-run only the door rule on existing tracks with per-camera overrides and score it
against the MEVA door annotations (+/-2 s, the evaluator's tolerance). Tune on the tuning window only; the
held-out windows are scored once, as they are, to check a change.

Usage (from backend/):  python -m argus.vision.door_eval                       # current settings, tuning window
                        python -m argus.vision.door_eval G331=leaf             # try the leaf method on G331
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

from argus import settings
from argus.config import site
from argus.eval.evaluate import DOOR_TOL_S
from argus.ingest.groundtruth import load_door_truth
from argus.vision import rules
from argus.vision.common import camera_cfg

DOOR_CAMS = ("G331", "G419", "G420", "G421", "G638")


def door_events(track_files: list[Path], tracks_dir: Path, overrides: dict[str, dict]) -> dict[str, list[float]]:
    zoned = rules.camera_cfg
    old_dir = rules.TRACKS_DIR
    rules.camera_cfg = lambda cam: {**zoned(cam), **overrides.get(cam, {})}
    rules.TRACKS_DIR = tracks_dir
    out: dict[str, list[float]] = defaultdict(list)
    try:
        for p in track_files:
            r = rules.ClipRules(p)
            for e in r.run():
                if e["type"] == "door_activity":
                    out[e["sensor_id"]].append(e["t"])
    finally:
        rules.camera_cfg, rules.TRACKS_DIR = zoned, old_dir
    return out


def score(det: dict[str, list[float]], truth: dict[str, list[float]], start: float, end: float) -> dict:
    rows, tp_all, n_det, n_truth = {}, 0, 0, 0
    for cam in sorted(set(det) | set(truth)):
        d = sorted(t for t in det.get(cam, []) if start <= t <= end)
        g = sorted(t for t in truth.get(cam, []) if start <= t <= end)
        used, tp = [False] * len(d), 0
        for t in g:
            best = min((i for i in range(len(d)) if not used[i] and abs(d[i] - t) <= DOOR_TOL_S),
                       key=lambda i: abs(d[i] - t), default=None)
            if best is not None:
                used[best], tp = True, tp + 1
        rows[cam] = {"truth": len(g), "detected": len(d), "tp": tp}
        tp_all, n_det, n_truth = tp_all + tp, n_det + len(d), n_truth + len(g)
    return {"per_camera": rows, "tp": tp_all, "detected": n_det, "truth": n_truth,
            "precision": round(tp_all / n_det, 3) if n_det else None,
            "recall": round(tp_all / n_truth, 3) if n_truth else None}


def parse_overrides(args: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for a in args:
        cam, method = a.split("=")
        out[cam] = {"door_method": method}
    return out


def main(argv: list[str]) -> int:
    cfg = site()
    overrides = parse_overrides(argv)
    files = [p for p in sorted(settings.TRACKS_DIR.glob("*.jsonl")) if p.name.count(".") == 5
             and p.stem.split(".")[-1] in DOOR_CAMS]
    det = door_events(files, settings.TRACKS_DIR, overrides)
    start, end = cfg.local_to_epoch("2018-03-15 14:50:00"), cfg.local_to_epoch("2018-03-15 15:20:00")
    s = score(det, load_door_truth(settings.ANNOTATION_DIR, cfg), start, end)
    for cam, r in s["per_camera"].items():
        p = f"{r['tp'] / r['detected']:.2f}" if r["detected"] else "-"
        rc = f"{r['tp'] / r['truth']:.2f}" if r["truth"] else "-"
        print(f"  {cam}: truth {r['truth']:>3}  detected {r['detected']:>3}  correct {r['tp']:>3}  P {p}  R {rc}")
    print(f"ALL: P {s['precision']}  R {s['recall']}   ({s['tp']} correct of {s['detected']} detected, {s['truth']} truth)")
    print(json.dumps({"overrides": overrides}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
