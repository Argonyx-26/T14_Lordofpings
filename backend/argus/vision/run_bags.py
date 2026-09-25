"""Second, bag-only detection pass: yolo11m @1280, low confidence -> data/tracks/<stem>.bags.jsonl

Small bags on the floor (e.g. G421 theft 1) sit at conf 0.1-0.2, below what ByteTrack will start a
track on, so this pass writes raw per-frame detections and rules.py links them itself.

Usage: python backend/argus/vision/run_bags.py [clip.avi ...]   (default: all clips)
"""
import json
import pathlib
import sys
import time

from ultralytics import YOLO

ROOT = pathlib.Path(__file__).resolve().parents[3]
VIDEO_DIR = ROOT / "data" / "meva" / "video"
TRACK_DIR = ROOT / "data" / "tracks"
BAGS = [24, 26, 28]
VID_STRIDE = 2


def run(clip: pathlib.Path, out: pathlib.Path) -> None:
    model = YOLO(str(ROOT / "models" / "yolo11m.pt"))
    tmp = out.with_suffix(".part")
    t0, n = time.time(), 0
    with tmp.open("w") as f:
        for i, r in enumerate(model.predict(source=str(clip), stream=True, classes=BAGS, conf=0.1, imgsz=1280,
                                            half=True, vid_stride=VID_STRIDE, verbose=False)):
            n = i + 1
            for box, cls, cf in zip(r.boxes.xyxy.tolist(), r.boxes.cls.int().tolist(), r.boxes.conf.tolist()):
                f.write(json.dumps({"frame": i * VID_STRIDE, "cls": cls, "conf": round(cf, 3),
                                    "xyxy": [round(v, 1) for v in box]}) + "\n")
    tmp.replace(out)
    dt = time.time() - t0
    print(f"{clip.stem}: {n} frames in {dt:.0f}s ({n / dt:.0f} fps) -> {out}", flush=True)


if __name__ == "__main__":
    TRACK_DIR.mkdir(parents=True, exist_ok=True)
    clips = [pathlib.Path(p) for p in sys.argv[1:]] or sorted(VIDEO_DIR.glob("*.avi"), key=lambda p: "G421" not in p.stem)
    for clip in clips:
        if clip.stem.endswith("G474"):
            continue
        out = TRACK_DIR / f"{clip.stem}.bags.jsonl"
        if out.exists():
            print(f"skip {clip.stem} (exists)")
            continue
        run(clip, out)
