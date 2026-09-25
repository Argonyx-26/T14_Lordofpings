"""Offline YOLO + ByteTrack over MEVA clips -> data/tracks/<stem>.jsonl (one line per frame per track).

Usage:
  python -m backend.argus.vision.run_tracks                  # all clips, G421 first
  python -m backend.argus.vision.run_tracks <clip.avi> ...   # specific clips
"""
import json
import pathlib
import sys
import time

from ultralytics import YOLO

ROOT = pathlib.Path(__file__).resolve().parents[3]
VIDEO_DIR = ROOT / "data" / "meva" / "video"
TRACK_DIR = ROOT / "data" / "tracks"
WEIGHTS = str(ROOT / "models" / "yolo11s.pt")
CLASSES = [0, 2, 3, 5, 7, 24, 26, 28]  # person, car, motorcycle, bus, truck, backpack, handbag, suitcase
VID_STRIDE = 2


def run(clip: pathlib.Path, out: pathlib.Path, weights: str = WEIGHTS) -> None:
    model = YOLO(weights)  # one model instance per clip so tracker state is fresh
    tmp = out.with_suffix(".jsonl.part")
    t0, n = time.time(), 0
    with tmp.open("w") as f:
        for i, r in enumerate(model.track(source=str(clip), stream=True, persist=True, tracker="bytetrack.yaml",
                                          classes=CLASSES, conf=0.3, imgsz=960, half=True,
                                          vid_stride=VID_STRIDE, verbose=False)):
            n = i + 1
            if r.boxes.id is None:
                continue
            frame = i * VID_STRIDE  # original frame index
            for box, tid, cls, cf in zip(r.boxes.xyxy.tolist(), r.boxes.id.int().tolist(),
                                         r.boxes.cls.int().tolist(), r.boxes.conf.tolist()):
                f.write(json.dumps({"frame": frame, "tid": tid, "cls": cls, "conf": round(cf, 3),
                                    "xyxy": [round(v, 1) for v in box]}) + "\n")
    tmp.replace(out)
    dt = time.time() - t0
    print(f"{clip.stem}: {n} frames in {dt:.0f}s ({n / dt:.0f} fps) -> {out}", flush=True)


if __name__ == "__main__":
    TRACK_DIR.mkdir(parents=True, exist_ok=True)
    clips = [pathlib.Path(p) for p in sys.argv[1:]] or sorted(VIDEO_DIR.glob("*.avi"), key=lambda p: "G421" not in p.stem)
    for clip in clips:
        if clip.stem.endswith("G474"):  # IR pair of G336, low-res, no annotations
            continue
        out = TRACK_DIR / f"{clip.stem}.jsonl"
        if out.exists():
            print(f"skip {clip.stem} (exists)")
            continue
        run(clip, out)
