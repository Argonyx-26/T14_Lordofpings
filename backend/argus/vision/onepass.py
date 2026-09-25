"""One decode, every model: the tracking, valuables, pose and weapon passes over a video in a single read.

The separate passes (run_tracks / run_bags / run_pose / run_weapons, and uploads.py's copies) each decode the whole
video again. Here a reader thread decodes each analysed frame once (grab() for the skipped ones) while the GPU runs
the models on the previous frame, and each model writes the same rows, to the same files, as its own pass would.
Nothing downstream changes: rules.py, threats.py and violence_videomae.py read these files as before.

    from argus.vision.onepass import Pass, run
    run(video, [Pass("tracks", "models/yolo11s.pt", out, track=True, classes=[...], conf=0.3, imgsz=960), ...],
        stride=2, frame_of=lambda orig: orig)

Usage (benchmark against the separate passes):  python -m argus.vision.onepass <clip> [--seconds 60]
"""
from __future__ import annotations

import json
import queue
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass
class Pass:
    name: str
    weights: str
    out: Path
    track: bool = False                 # ByteTrack ids (tracks, pose) or raw per-frame detections (bags, weapons)
    classes: list[int] | None = None
    conf: float = 0.25
    imgsz: int = 960
    pose: bool = False                  # write keypoints
    model: object = field(default=None, repr=False)


def _reader(path: str, stride: int, q: queue.Queue, limit: int | None) -> None:
    import cv2
    cap = cv2.VideoCapture(path)
    i = 0
    try:
        while limit is None or i < limit:
            if i % stride:
                if not cap.grab():
                    break
            else:
                ok, img = cap.read()
                if not ok:
                    break
                q.put((i, img))
            i += 1
    finally:
        cap.release()
        q.put(None)


def run(video: Path, passes: list[Pass], stride: int, frame_of: Callable[[int], int],
        box_scale: tuple[float, float] = (1.0, 1.0), progress: Callable[[int], None] | None = None,
        limit_frames: int | None = None) -> int:
    """Returns the last original frame index analysed. frame_of maps it to the frame number written in the rows."""
    import torch
    from ultralytics import YOLO
    half = torch.cuda.is_available()
    for p in passes:
        p.model = p.model or YOLO(p.weights)
    sx, sy = box_scale
    q: queue.Queue = queue.Queue(maxsize=8)
    threading.Thread(target=_reader, args=(str(video), stride, q, limit_frames), daemon=True).start()
    files = {p.name: p.out.with_suffix(".part").open("w", encoding="utf-8") for p in passes}
    last = 0

    def box(b):
        return [round(b[0] * sx, 1), round(b[1] * sy, 1), round(b[2] * sx, 1), round(b[3] * sy, 1)]
    try:
        while (item := q.get()) is not None:
            orig, img = item
            last, frame = orig, frame_of(orig)
            for p in passes:
                kw = dict(conf=p.conf, imgsz=p.imgsz, half=half, verbose=False)
                if p.classes is not None:
                    kw["classes"] = p.classes
                r = (p.model.track(img, persist=True, tracker="bytetrack.yaml", **kw) if p.track
                     else p.model.predict(img, **kw))[0]
                f = files[p.name]
                if r.boxes is None or (p.track and r.boxes.id is None):
                    continue
                ids = r.boxes.id.int().tolist() if p.track else [None] * len(r.boxes)
                kps = r.keypoints.data.tolist() if p.pose and r.keypoints is not None else None
                for k, (b, tid, cls, cf) in enumerate(zip(r.boxes.xyxy.tolist(), ids, r.boxes.cls.int().tolist(),
                                                          r.boxes.conf.tolist())):
                    row = {"frame": frame}
                    if tid is not None:
                        row["tid"] = tid
                    if not p.pose:
                        row["cls"] = cls
                    row["conf"] = round(cf, 3)
                    row["xyxy"] = box(b)
                    if kps is not None:
                        row["kp"] = [[round(x * sx, 1), round(y * sy, 1), round(c, 2)] for x, y, c in kps[k]]
                    f.write(json.dumps(row) + "\n")
            if progress:
                progress(orig)
    finally:
        for f in files.values():
            f.close()
    for p in passes:
        p.out.with_suffix(".part").replace(p.out)
    return last


if __name__ == "__main__":
    import argparse
    import sys
    import tempfile

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from argus.vision import run_bags, run_pose, run_tracks, run_weapons

    ap = argparse.ArgumentParser()
    ap.add_argument("clip")
    ap.add_argument("--seconds", type=float, default=60)
    a = ap.parse_args()
    clip = Path(a.clip)
    models = Path(__file__).resolve().parents[3] / "models"
    tmp = Path(tempfile.mkdtemp())
    import cv2
    fps = cv2.VideoCapture(str(clip)).get(cv2.CAP_PROP_FPS) or 30
    n = int(a.seconds * fps)
    cut = tmp / f"{clip.stem}.mp4"                     # the same frames for both runs
    w = None
    cap = cv2.VideoCapture(str(clip))
    for _ in range(n):
        ok, img = cap.read()
        if not ok:
            break
        if w is None:
            w = cv2.VideoWriter(str(cut), cv2.VideoWriter_fourcc(*"mp4v"), fps, (img.shape[1], img.shape[0]))
        w.write(img)
    w.release()
    sep = {k: tmp / f"sep.{k}.jsonl" for k in ("tracks", "bags", "pose", "weapons")}
    t0 = time.time()
    run_tracks.run(cut, sep["tracks"])
    run_bags.run(cut, sep["bags"])
    run_pose.run(cut, sep["pose"])
    run_weapons.run(cut, sep["weapons"])
    t_sep = time.time() - t0
    one = {k: tmp / f"one.{k}.jsonl" for k in sep}
    t0 = time.time()
    run(cut, [Pass("tracks", run_tracks.WEIGHTS, one["tracks"], track=True, classes=run_tracks.CLASSES, conf=0.3),
              Pass("bags", str(models / "yolo11m.pt"), one["bags"], classes=run_bags.BAGS, conf=0.1, imgsz=1280),
              Pass("pose", str(run_pose.WEIGHTS), one["pose"], track=True, pose=True),
              Pass("weapons", str(run_weapons.WEIGHTS), one["weapons"], conf=run_weapons.CONF)],
        stride=2, frame_of=lambda orig: orig)
    t_one = time.time() - t0

    def rows(p):
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]
    report = {"clip": clip.stem, "seconds_of_video": round(n / fps, 1),
              "separate_s": round(t_sep, 1), "one_pass_s": round(t_one, 1), "speedup": round(t_sep / t_one, 2),
              "rows": {k: [len(rows(sep[k])), len(rows(one[k]))] for k in sep},
              "identical": {k: rows(sep[k]) == rows(one[k]) for k in sep}}
    print(json.dumps(report, indent=1))
