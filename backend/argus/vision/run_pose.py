"""Pose pass: YOLO11s-pose + ByteTrack -> <stem>.pose.jsonl (one line per tracked person per analysed frame).

Feeds the violence rule (vision/violence.py): fights, strikes and people on the ground are read from how bodies
move relative to each other, not from a single frame.

Usage:  python backend/argus/vision/run_pose.py <clip> [<clip> ...]      (writes next to data/tracks/<stem>.pose.jsonl)
"""
import json
import pathlib
import sys
import time

from ultralytics import YOLO

ROOT = pathlib.Path(__file__).resolve().parents[3]
WEIGHTS = ROOT / "models" / "yolo11s-pose.pt"
TRACK_DIR = ROOT / "data" / "tracks"


def run(clip: pathlib.Path, out: pathlib.Path, stride: int = 2, imgsz: int = 960, fps: float | None = None,
        frame_scale: float = 1.0, model: YOLO | None = None) -> None:
    """stride: analyse every Nth frame. Rows carry the clip's own frame index times frame_scale (uploads map their
    frames onto the rules' 30 fps clock), boxes and keypoints in the clip's pixels. Pass a loaded model to reuse
    it across many short clips (the tracker still starts fresh for each clip)."""
    model = model or YOLO(str(WEIGHTS))
    if hasattr(model, "predictor") and model.predictor is not None and hasattr(model.predictor, "trackers"):
        del model.predictor.trackers                  # fresh ByteTrack state for this clip
    tmp = out.with_suffix(".part")
    t0, n = time.time(), 0
    with tmp.open("w", encoding="utf-8") as f:
        for i, r in enumerate(model.track(source=str(clip), stream=True, persist=True, tracker="bytetrack.yaml",
                                          conf=0.25, imgsz=imgsz, half=True, vid_stride=stride, verbose=False)):
            n = i + 1
            if r.boxes.id is None or r.keypoints is None:
                continue
            frame = round(i * stride * frame_scale)
            kps = r.keypoints.data.tolist()
            for box, tid, cf, kp in zip(r.boxes.xyxy.tolist(), r.boxes.id.int().tolist(), r.boxes.conf.tolist(), kps):
                f.write(json.dumps({"frame": frame, "tid": tid, "conf": round(cf, 3),
                                    "xyxy": [round(v, 1) for v in box],
                                    "kp": [[round(x, 1), round(y, 1), round(c, 2)] for x, y, c in kp]}) + "\n")
    tmp.replace(out)
    dt = time.time() - t0
    print(f"{clip.stem}: {n} frames in {dt:.0f}s ({n / max(dt, 1e-6):.0f} fps) -> {out}", flush=True)


if __name__ == "__main__":
    TRACK_DIR.mkdir(parents=True, exist_ok=True)
    for c in [pathlib.Path(p) for p in sys.argv[1:]]:
        o = TRACK_DIR / f"{c.stem}.pose.jsonl"
        if not o.exists():
            run(c, o)
