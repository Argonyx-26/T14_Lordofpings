"""Scores for the pose rules that had none: person_down and hand_off (vision/threats.py), unchanged.

person_down  UR Fall Detection Dataset (Kwolek & Kepski 2014; fenix.ur.edu.pl/~mkepski/ds/uf.html), camera 0:
             30 falls and 40 everyday activities (walking, sitting, crouching, picking things up, and lying down on a
             bed or sofa: hard negatives). A fall clip counts as caught if person_down fires in it; an activity
             clip that fires is a false alarm. Pose pass: the same YOLO11s-pose, stride 2, as the pipeline.
hand_off     MEVA person_transfers_object annotations on the demo-window clips that have pose data. Found if a
             hand-off starts inside an annotated transfer (+/-2 s, as eval/scale.py); a hand-off is correct if
             it falls inside any transfer.

Usage (from backend/):  python -m argus.eval.threats_eval falls      (data/train/urfd/*.mp4, pose cached)
                        python -m argus.eval.threats_eval handoffs   (pose in data/eval/handoff/)
Writes data/cache/threats_eval.json (merged across runs).
"""
import json
import sys
import time
from pathlib import Path

from argus import settings
from argus.vision import threats

ROOT = settings.REPO_ROOT
OUT = settings.CACHE_DIR / "threats_eval.json"
TOL_S = 2.0


class Collector:
    """Stands in for ClipRules: the pose rules only call emit()."""

    def __init__(self, cam="EVAL"):
        self.cam, self.events = cam, []

    def emit(self, type_, frame, severity, confidence, entity_id, bbox=None, kind="track", **attrs):
        self.events.append({"type": type_, "frame": frame, "tid": entity_id, "bbox": bbox, **attrs})


def _rows(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.open(encoding="utf-8")]


def _save(key: str, value: dict) -> None:
    data = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    data[key] = {**value, "when": time.strftime("%Y-%m-%d %H:%M")}
    OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")


def falls() -> dict:
    from argus.vision import run_pose
    src = ROOT / "data" / "train" / "urfd"
    cache = ROOT / "data" / "train" / "urfd_pose"
    cache.mkdir(parents=True, exist_ok=True)
    model = None
    rows_out = []
    for clip in sorted(src.glob("*.mp4")):
        pose = cache / f"{clip.stem}.pose.jsonl"
        if not pose.exists():
            from ultralytics import YOLO
            model = model or YOLO(str(run_pose.WEIGHTS))
            run_pose.run(clip, pose, stride=2, model=model)
        c = Collector()
        threats.person_down(c, _rows(pose))
        fired = [e for e in c.events if e["type"] == "person_down"]
        rows_out.append({"clip": clip.stem, "fall": clip.stem.startswith("fall"), "fired": bool(fired),
                         "at_s": round(fired[0]["frame"] / 30, 1) if fired else None})
        print(f"{clip.stem:<14} {'FALL' if rows_out[-1]['fall'] else 'adl ':<5} -> "
              f"{'person_down at ' + str(rows_out[-1]['at_s']) + ' s' if fired else '-'}", flush=True)
    f = [r for r in rows_out if r["fall"]]
    a = [r for r in rows_out if not r["fall"]]
    tp, fp = sum(r["fired"] for r in f), sum(r["fired"] for r in a)
    res = {"dataset": "UR Fall Detection (cam0)", "falls": len(f), "activities": len(a),
           "falls_caught": tp, "activities_flagged": fp,
           "recall": round(tp / max(len(f), 1), 3), "precision": round(tp / max(tp + fp, 1), 3),
           "flagged_activities": [r["clip"] for r in a if r["fired"]],
           "missed_falls": [r["clip"] for r in f if not r["fired"]],
           "rule": f"box wider than tall and torso tilt >= {threats.DOWN_TILT} deg for >= {threats.DOWN_S} s"}
    _save("person_down", res)
    return res


def handoffs(pose_dir: Path = ROOT / "data" / "eval" / "handoff") -> dict:
    from argus.ingest.doors import _activities
    per, truth_n, found, det_n, correct = [], 0, 0, 0, 0
    for pose in sorted(pose_dir.glob("*.pose.jsonl")):
        stem = pose.name.removesuffix(".pose.jsonl")
        spans = [(s / 30.0, e / 30.0) for _, label, s, e in _activities(settings.ANNOTATION_DIR / f"{stem}.activities.yml")
                 if label == "person_transfers_object"]
        c = Collector(stem.split(".")[-1])
        threats.hand_off(c, _rows(pose))
        det = [e["frame"] / 30.0 for e in c.events if e["type"] == "hand_off"]
        f = sum(any(s - TOL_S <= d <= e + TOL_S for d in det) for s, e in spans)
        k = sum(any(s - TOL_S <= d <= e + TOL_S for s, e in spans) for d in det)
        truth_n, found, det_n, correct = truth_n + len(spans), found + f, det_n + len(det), correct + k
        per.append({"clip": stem, "transfers": len(spans), "found": f, "hand_offs": len(det), "correct": k})
        print(f"{stem:<44} transfers {len(spans):>2}  found {f:>2}  hand-offs {len(det):>3}  correct {k:>3}", flush=True)
    res = {"dataset": "MEVA demo window (person_transfers_object)", "clips": len(per), "transfers": truth_n,
           "found": found, "recall": round(found / max(truth_n, 1), 3), "hand_offs": det_n, "correct": correct,
           "precision": round(correct / max(det_n, 1), 3), "per_clip": per, "tolerance_s": TOL_S}
    _save("hand_off", res)
    return res


if __name__ == "__main__":
    print(json.dumps({"falls": falls, "handoffs": handoffs}[sys.argv[1]](), indent=1))
