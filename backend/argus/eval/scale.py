"""Large-sample evaluation on MEVA footage outside every window used for tuning or held-out testing.

scale_clips.json lists 306 annotated 5-minute clips from seven days on the indoor/plaza cameras (G419, G420,
G421, G638): 1,337 annotated door openings and 176 hand-to-hand transfers. For each clip this downloads the video
and annotations, checks the camera still has the tuned view (a re-aimed camera would make zones meaningless),
runs the unchanged pipeline (main pass, door-leaf sensor, pose pass, rules) and scores:
  doors      door_activity vs person_opens_facility_door, +/-2 s (the evaluator's tolerance)
  hand-offs  hand_off vs person_transfers_object, counted as found if a hand-off starts inside the annotated
             transfer (+/-2 s)

Usage (repo root):  python -m argus.eval.scale --per-camera 5        # a sample: 5 clips per camera
                    python -m argus.eval.scale --per-camera 80       # everything (a GPU server with fast internet)
Writes data_scale/results.json and docs/SCALE_RESULTS.md. Resumable: finished clips are skipped.
"""
import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
os.environ.setdefault("ARGUS_DATA", str(REPO / "data_scale"))

from argus import settings  # noqa: E402
from argus.config import site  # noqa: E402
from argus.ingest.clips import parse_clip  # noqa: E402
from argus.ingest.doors import _activities  # noqa: E402

S3 = "https://mevadata-public-01.s3.amazonaws.com/drops-123-r13"
ANN = "https://gitlab.kitware.com/meva/meva-data-repo/-/raw/master/annotation/DIVA-phase-2/MEVA"
ROOT = settings.DATA_DIR
VIDEO, TRACKS, ANN_DIR = ROOT / "video", settings.TRACKS_DIR, ROOT / "ann"
REF_VIDEO = REPO / "data" / "meva" / "video"
TOL_S = 2.0
VIEW_MAX_SHIFT = 8.0         # px at 480 px width; more than this and the camera was re-aimed


def log(msg: str) -> None:
    print(f"[scale {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _get(url: str, dest: Path) -> bool:
    import httpx
    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for _ in range(3):
        try:
            with httpx.stream("GET", url, follow_redirects=True, timeout=120) as r:
                if r.status_code != 200:
                    return False
                with tmp.open("wb") as f:
                    for chunk in r.iter_bytes(1 << 20):
                        f.write(chunk)
            tmp.replace(dest)
            return True
        except Exception:
            time.sleep(3)
    return False


def _frame(path: Path, n: int = 150):
    import cv2
    cap = cv2.VideoCapture(str(path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, n)
    ok, img = cap.read()
    cap.release()
    return img if ok else None


def view_shift(clip: Path, cam: str) -> float:
    """How far (pixels at 480 px width) the scene has moved against the tuned 15 March view, by phase correlation of
    edge maps. Lighting, shadows and crowds barely move the peak; a re-aimed camera does (checked on the known
    cases: G331 and G336 re-aimed on 5 March shift 26 and 77 px, same-view clips 0-3 px)."""
    import cv2
    import numpy as np
    ref = next(iter(sorted(REF_VIDEO.glob(f"2018-03-15*{cam}.avi"))), None)
    a, b = (_frame(p) for p in (ref, clip)) if ref else (None, None)
    if a is None or b is None:
        return 999.0

    def edges(img):
        g = cv2.cvtColor(cv2.resize(img, (480, 268)), cv2.COLOR_BGR2GRAY)
        e = cv2.Canny(cv2.GaussianBlur(g, (5, 5), 0), 50, 150).astype(np.float32)
        return cv2.GaussianBlur(e, (7, 7), 0)
    (dx, dy), _ = cv2.phaseCorrelate(edges(a), edges(b), cv2.createHanningWindow((480, 268), cv2.CV_32F))
    return float(np.hypot(dx, dy))


def process(row: dict) -> dict | None:
    import numpy as np
    from argus.vision import door_sensor, rules, run_pose, run_tracks, run_weapons
    from argus.vision.common import camera_cfg

    stem, cam = row["stem"], row["cam"]
    done = ROOT / "done" / f"{stem}.json"
    if done.exists():
        return json.loads(done.read_text(encoding="utf-8"))
    video, ann = VIDEO / f"{stem}.avi", ANN_DIR / f"{stem}.activities.yml"
    if not _get(f"{ANN}/{row['set']}/{row['date']}/{row['hour']}/{stem}.activities.yml", ann):
        return None
    if not _get(f"{S3}/{row['date']}/{row['hour']}/{stem}.r13.avi", video):
        return None
    shift = view_shift(video, cam)
    res = {"stem": stem, "cam": cam, "view_shift_px": round(shift, 1), "same_view": shift <= VIEW_MAX_SHIFT}
    if res["same_view"]:
        TRACKS.mkdir(parents=True, exist_ok=True)
        main, pose, doors = TRACKS / f"{stem}.jsonl", TRACKS / f"{stem}.pose.jsonl", TRACKS / f"{stem}.doors.npz"
        if not main.exists():
            run_tracks.run(video, main, str(REPO / "models" / "yolo11s.pt"))
        if not pose.exists():
            run_pose.run(video, pose)
        weapons = TRACKS / f"{stem}.weapons.jsonl"
        if run_weapons.available() and not weapons.exists():
            run_weapons.run(video, weapons)
        leaves = camera_cfg(cam).get("door_leaf") or {}
        if leaves and not doors.exists():
            frames, sig = door_sensor.signals(video, leaves)
            np.savez(doors, frames=frames, **sig)
        rules.TRACKS_DIR = TRACKS
        events = rules.ClipRules(main).run()
        clip = parse_clip(stem, site())
        truth_doors, truth_tx = [], []
        for _, label, s, e in _activities(ann):
            if label == "person_opens_facility_door":
                truth_doors.append(clip.start_t + s / 30.0)
            elif label == "person_transfers_object":
                truth_tx.append((clip.start_t + s / 30.0, clip.start_t + e / 30.0))
        res.update(
            doors_truth=len(truth_doors), doors_det=sum(e["type"] == "door_activity" for e in events),
            doors_tp=_match_points([e["t"] for e in events if e["type"] == "door_activity"], truth_doors),
            tx_truth=len(truth_tx), tx_det=sum(e["type"] == "hand_off" for e in events),
            **_match_spans([e["t"] for e in events if e["type"] == "hand_off"], truth_tx),
            threats={t: sum(e["type"] == t for e in events) for t in ("weapon_visible", "violence", "person_down",
                                                                     "dealing_pattern")},
            threat_events=[{"type": e["type"], "t": e["t"], "attrs": e["attrs"]} for e in events
                           if e["type"] in ("weapon_visible", "violence", "person_down", "dealing_pattern")],
        )
    done.parent.mkdir(parents=True, exist_ok=True)
    done.write_text(json.dumps(res), encoding="utf-8")
    if os.environ.get("ARGUS_SCALE_KEEP_VIDEO") != "1":
        video.unlink(missing_ok=True)                  # 100 MB per clip: keep the disk free
    return res


def _match_points(det: list[float], truth: list[float]) -> int:
    used, tp = [False] * len(det), 0
    for g in sorted(truth):
        best = min((i for i in range(len(det)) if not used[i] and abs(det[i] - g) <= TOL_S),
                   key=lambda i: abs(det[i] - g), default=None)
        if best is not None:
            used[best], tp = True, tp + 1
    return tp


def _match_spans(det: list[float], spans: list[tuple[float, float]]) -> dict:
    found = sum(any(s - TOL_S <= d <= e + TOL_S for d in det) for s, e in spans)
    correct = sum(any(s - TOL_S <= d <= e + TOL_S for s, e in spans) for d in det)
    return {"tx_found": found, "tx_det_correct": correct}


def summarise(results: list[dict]) -> dict:
    same = [r for r in results if r.get("same_view")]
    by_cam = defaultdict(lambda: defaultdict(int))
    for r in same:
        for k in ("doors_truth", "doors_det", "doors_tp", "tx_truth", "tx_det", "tx_found", "tx_det_correct"):
            by_cam[r["cam"]][k] += r.get(k, 0)
        by_cam[r["cam"]]["clips"] += 1
    tot = defaultdict(int)
    for c in by_cam.values():
        for k, v in c.items():
            tot[k] += v
    threats = defaultdict(int)
    for r in same:
        for k, v in (r.get("threats") or {}).items():
            threats[k] += v

    def pr(tp, det, truth):
        return (round(tp / det, 3) if det else None), (round(tp / truth, 3) if truth else None)
    return {
        "clips_scored": len(same), "clips_view_changed": len(results) - len(same),
        "camera_hours": round(len(same) * 5 / 60, 2),
        "doors": dict(zip(("precision", "recall"), pr(tot["doors_tp"], tot["doors_det"], tot["doors_truth"])),
                      truth=tot["doors_truth"], detected=tot["doors_det"]),
        "hand_offs": {"precision": pr(tot["tx_det_correct"], tot["tx_det"], 0)[0],
                      "recall": pr(tot["tx_found"], 1, tot["tx_truth"])[1],
                      "truth": tot["tx_truth"], "found": tot["tx_found"], "detected": tot["tx_det"]},
        "per_camera": {k: dict(v) for k, v in by_cam.items()},
        "threat_events_on_normal_footage": dict(threats),
    }


def write_report(s: dict) -> Path:
    d, h = s["doors"], s["hand_offs"]
    rec = h["recall"]
    lines = [
        "# Large-sample results (MEVA, outside every tuning and held-out window)", "",
        f"{s['clips_scored']} five-minute clips ({s['camera_hours']} camera-hours) on G419, G420, G421 and G638, "
        f"from seven days. {s['clips_view_changed']} clips were skipped because the camera had been re-aimed. "
        "Produced by `python -m argus.eval.scale`.", "",
        "| Detector | Annotated events | Detected | Precision | Recall |", "|---|---|---|---|---|",
        f"| Door opening (video door sensor) | {d['truth']} | {d['detected']} | {d['precision']} | {d['recall']} |",
        f"| Hand-to-hand exchange | {h['truth']} | {h['detected']} | {h['precision']} | {rec} |", "",
        "False threat events on this ordinary footage (MEVA has no weapons, fights or dealing): "
        + ", ".join(f"{k} {v}" for k, v in s["threat_events_on_normal_footage"].items()) + ".", "",
        "| Camera | Clips | Doors (truth / detected / correct) | Hand-offs (truth / found / detected) |",
        "|---|---|---|---|",
    ]
    for cam, c in sorted(s["per_camera"].items()):
        lines.append(f"| {cam} | {c['clips']} | {c['doors_truth']} / {c['doors_det']} / {c['doors_tp']} | "
                     f"{c['tx_truth']} / {c['tx_found']} / {c['tx_det']} |")
    out = REPO / "docs" / "SCALE_RESULTS.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-camera", type=int, default=5)
    ap.add_argument("--cameras", nargs="*", default=["G419", "G420", "G421", "G638"])
    args = ap.parse_args(argv)
    rows = json.loads((Path(__file__).with_name("scale_clips.json")).read_text(encoding="utf-8"))
    picked = []
    for cam in args.cameras:
        picked += [r for r in rows if r["cam"] == cam][:args.per_camera]
    log(f"{len(picked)} clips; data root {ROOT}")
    results = []
    for i, row in enumerate(picked, 1):
        t0 = time.time()
        r = process(row)
        if r:
            results.append(r)
            log(f"{i}/{len(picked)} {row['stem']} view shift {r['view_shift_px']} "
                f"doors {r.get('doors_tp', '-')}/{r.get('doors_truth', '-')} tx {r.get('tx_found', '-')}/"
                f"{r.get('tx_truth', '-')} ({time.time() - t0:.0f} s)")
        s = summarise(results)
        (ROOT / "results.json").write_text(json.dumps({"summary": s, "clips": results}, indent=1), encoding="utf-8")
    log(f"report: {write_report(summarise(results))}")
    print(json.dumps(summarise(results), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
