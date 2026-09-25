"""How many cameras one GPU can analyse: throughput of the two detection passes at the settings the rules were
tuned on (main pass yolo11s @960 + ByteTrack, valuables pass yolo11m @1280, both FP16, every 2nd frame = 15 fps
per camera). Run it with nothing else on the GPU (stop the live tile and any upload or held-out job first).

Usage:  python backend/argus/vision/bench.py [clip.avi]     (default: the busiest demo clip, the G421 cafe)
Writes data/cache/bench.json.
"""
import json
import pathlib
import sys
import time

import cv2
import torch
from ultralytics import YOLO

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from argus import settings  # noqa: E402
from argus.vision import run_bags, run_tracks  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[3]
N_FRAMES = 300
ANALYSED_FPS = 30 / run_tracks.VID_STRIDE        # what the rules see per camera


def load_frames(clip: pathlib.Path, n: int) -> list:
    cap, out = cv2.VideoCapture(str(clip)), []
    while len(out) < n:
        ok, f = cap.read()
        if not ok:
            break
        out.append(f)
    cap.release()
    return out


def decode_fps(clip: pathlib.Path, n: int) -> float:
    cap, t0, k = cv2.VideoCapture(str(clip)), time.perf_counter(), 0
    while k < n and cap.grab():
        cap.retrieve()
        k += 1
    cap.release()
    return k / (time.perf_counter() - t0)


def throughput(model: YOLO, frames: list, batch: int, **kw) -> float:
    model.predict(frames[:batch], verbose=False, **kw)                 # warm-up
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    for i in range(0, len(frames), batch):
        model.predict(frames[i:i + batch], verbose=False, **kw)
    torch.cuda.synchronize()
    return len(frames) / (time.perf_counter() - t0)


def tracking_fps(frames: list) -> float:
    """The main pass as the pipeline runs it: detection + ByteTrack, one frame at a time."""
    model = YOLO(str(ROOT / "models" / "yolo11s.pt"))
    kw = dict(persist=True, tracker="bytetrack.yaml", classes=run_tracks.CLASSES, conf=0.3, imgsz=960,
              half=True, verbose=False)
    model.track(frames[0], **kw)
    torch.cuda.synchronize()
    t0 = time.perf_counter()
    for f in frames:
        model.track(f, **kw)
    torch.cuda.synchronize()
    return len(frames) / (time.perf_counter() - t0)


def main(argv: list[str]) -> int:
    clip = pathlib.Path(argv[0]) if argv else next((settings.MEVA_DIR / "video").glob("*G421.avi"))
    frames = load_frames(clip, N_FRAMES)
    main_kw = dict(classes=run_tracks.CLASSES, conf=0.3, imgsz=960, half=True)
    bag_kw = dict(classes=run_bags.BAGS, conf=0.1, imgsz=1280, half=True)
    m, b = YOLO(str(ROOT / "models" / "yolo11s.pt")), YOLO(str(ROOT / "models" / "yolo11m.pt"))
    r = {
        "gpu": torch.cuda.get_device_name(0), "clip": clip.name, "frames": len(frames),
        "analysed_fps_per_camera": ANALYSED_FPS,
        "decode_fps_one_cpu_thread": round(decode_fps(clip, N_FRAMES), 1),
        "main_track_fps": round(tracking_fps(frames), 1),
        "main_detect_fps_batch1": round(throughput(m, frames, 1, **main_kw), 1),
        "main_detect_fps_batch8": round(throughput(m, frames, 8, **main_kw), 1),
        "bags_fps_batch1": round(throughput(b, frames, 1, **bag_kw), 1),
        "bags_fps_batch8": round(throughput(b, frames, 8, **bag_kw), 1),
    }

    def cams(main_fps, bag_fps):
        return round(1 / (ANALYSED_FPS / main_fps + ANALYSED_FPS / bag_fps), 2)

    r["cameras_per_gpu_as_run"] = cams(r["main_track_fps"], r["bags_fps_batch1"])
    r["cameras_per_gpu_batched"] = cams(r["main_detect_fps_batch8"], r["bags_fps_batch8"])
    r["cameras_per_gpu_main_pass_only_batched"] = round(r["main_detect_fps_batch8"] / ANALYSED_FPS, 2)
    for k, v in r.items():
        print(f"{k:<40} {v}")
    settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (settings.CACHE_DIR / "bench.json").write_text(json.dumps(r, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
