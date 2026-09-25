"""Weapon pass: the fine-tuned CCTV weapon detector (train_weapons.py) -> <stem>.weapons.jsonl, raw per-frame boxes.

Low confidence on purpose: threats.py decides what counts (a weapon on a person, seen on several frames).

Usage:  python backend/argus/vision/run_weapons.py <clip> [<clip> ...]     (writes data/tracks/<stem>.weapons.jsonl)
"""
import json
import pathlib
import sys
import time

from ultralytics import YOLO

ROOT = pathlib.Path(__file__).resolve().parents[3]
WEIGHTS = ROOT / "models" / "weapons_yolo11s.pt"
TRACK_DIR = ROOT / "data" / "tracks"
CONF, IMGSZ = 0.25, 960


def available() -> bool:
    return WEIGHTS.exists()


def run(clip: pathlib.Path, out: pathlib.Path, stride: int = 2, frame_scale: float = 1.0, box_scale=(1.0, 1.0),
        model: YOLO | None = None) -> None:
    """Rows carry frame = clip frame x frame_scale and boxes x box_scale, so uploads land on the rules' canvas."""
    model = model or YOLO(str(WEIGHTS))
    sx, sy = box_scale
    tmp = out.with_suffix(".part")
    t0, n = time.time(), 0
    with tmp.open("w", encoding="utf-8") as f:
        for i, r in enumerate(model.predict(source=str(clip), stream=True, conf=CONF, imgsz=IMGSZ, half=True,
                                            vid_stride=stride, verbose=False)):
            n = i + 1
            for box, cls, cf in zip(r.boxes.xyxy.tolist(), r.boxes.cls.int().tolist(), r.boxes.conf.tolist()):
                f.write(json.dumps({"frame": round(i * stride * frame_scale), "cls": cls, "conf": round(cf, 3),
                                    "xyxy": [round(box[0] * sx, 1), round(box[1] * sy, 1),
                                             round(box[2] * sx, 1), round(box[3] * sy, 1)]}) + "\n")
    tmp.replace(out)
    dt = time.time() - t0
    print(f"{clip.stem}: {n} frames in {dt:.0f}s ({n / max(dt, 1e-6):.0f} fps) -> {out}", flush=True)


if __name__ == "__main__":
    TRACK_DIR.mkdir(parents=True, exist_ok=True)
    for c in [pathlib.Path(p) for p in sys.argv[1:]]:
        o = TRACK_DIR / f"{c.stem}.weapons.jsonl"
        if not o.exists():
            run(c, o)
