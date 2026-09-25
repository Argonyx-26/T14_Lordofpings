"""Motion-and-appearance evidence for violence: a pretrained VideoMAE surveillance violence classifier.

Model: HappyGook/videomae-violence-detector (MIT): VideoMAE-base fine-tuned on UCF-Crime, then on the Bus Violence
Dataset (real moving-bus CCTV). Class 1 = violent (model card). 16 frames per clip. Weights in models/videomae-violence/.
None of its training data is the fight dataset we test on, so scoring it alone there is an external test.

Usage (repo root):  python -m argus.vision.violence_videomae clips   (from backend/)  -> data/train/fights_vmae.json
"""
import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODEL_DIR = ROOT / "models" / "videomae-violence"
CACHE = ROOT / "data" / "train" / "fights_vmae.json"
FEATURES = ["vmae_p"]
N_FRAMES = 16

_m = None


def available() -> bool:
    return (MODEL_DIR / "model.safetensors").exists()


def _model():
    global _m
    if _m is None:
        import torch
        from transformers import VideoMAEForVideoClassification, VideoMAEImageProcessor
        proc = VideoMAEImageProcessor.from_pretrained(MODEL_DIR)
        model = VideoMAEForVideoClassification.from_pretrained(MODEL_DIR).eval()
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        _m = (proc, model.to(dev), dev)
    return _m


def prob(frames_bgr: list) -> float:
    """P(violent) for one window of frames (sampled to 16)."""
    import torch
    if not frames_bgr:
        return 0.0
    idx = np.linspace(0, len(frames_bgr) - 1, N_FRAMES).round().astype(int)
    frames = [np.ascontiguousarray(frames_bgr[i][:, :, ::-1]) for i in idx]
    proc, model, dev = _model()
    inputs = proc([frames], return_tensors="pt").to(dev)
    with torch.no_grad():
        return float(model(**inputs).logits.softmax(-1)[0, 1].cpu())


def read_frames(video: pathlib.Path) -> list:
    import cv2
    cap, frames = cv2.VideoCapture(str(video)), []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(f)
    cap.release()
    return frames


def score_clips() -> dict:
    fights = ROOT / "data" / "train" / "fights"
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    for folder in ("fight", "noFight"):
        for clip in sorted((fights / folder).glob("*")):
            if clip.stem not in cache:
                cache[clip.stem] = prob(read_frames(clip))
    CACHE.write_text(json.dumps(cache), encoding="utf-8")
    print(f"{len(cache)} clips scored -> {CACHE}")
    return cache




# ---- pipeline pass ---------------------------------------------------------------------------------------------
WIN_S, STEP_S = 2.5, 1.0


def _people_box(pose_rows_by_frame: dict, frame: int, w: int, h: int):
    """Square crop around the closest pair of people (or the only person) near this frame, padded 1.6x."""
    near = min(pose_rows_by_frame, key=lambda f: abs(f - frame), default=None)
    rows = pose_rows_by_frame.get(near, []) if near is not None and abs(near - frame) <= 30 else []
    if not rows:
        return None
    best, bd = rows[:1], 1e9
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = rows[i]["xyxy"], rows[j]["xyxy"]
            d = abs((a[0] + a[2]) - (b[0] + b[2])) + abs((a[1] + a[3]) - (b[1] + b[3]))
            if d < bd:
                best, bd = [rows[i], rows[j]], d
    x1 = min(r["xyxy"][0] for r in best); y1 = min(r["xyxy"][1] for r in best)
    x2 = max(r["xyxy"][2] for r in best); y2 = max(r["xyxy"][3] for r in best)
    side = max(x2 - x1, y2 - y1) * 1.6
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    side = min(side, w, h)
    l, t = int(min(max(0, cx - side / 2), w - side)), int(min(max(0, cy - side / 2), h - side))
    return l, t, int(side)


def run(video: pathlib.Path, pose: pathlib.Path, out: pathlib.Path, frame_scale: float = 1.0, box_scale=(1.0, 1.0)):
    """P(violent) every STEP_S over WIN_S windows, on a crop around the people (pose rows on the rules' canvas;
    box_scale maps canvas -> video pixels back). Rows: {frame (window centre, rules clock), p}."""
    import cv2
    from collections import defaultdict, deque
    rows = defaultdict(list)
    if pose.exists():
        for line in pose.open(encoding="utf-8"):
            r = json.loads(line)
            rows[r["frame"]].append(r)
    cap = cv2.VideoCapture(str(video))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    win, step = int(WIN_S * fps), int(STEP_S * fps)
    keep = max(1, win // N_FRAMES)                      # buffer only the frames VideoMAE will sample
    buf: deque = deque(maxlen=N_FRAMES + 1)
    sx, sy = box_scale
    i, out_rows = 0, []
    while True:
        ok = cap.grab()
        if not ok:
            break
        if i % keep == 0:
            buf.append((i, cap.retrieve()[1]))
        if i >= win and i % step == 0 and len(buf) >= N_FRAMES // 2:
            centre = i - win // 2
            canvas_frame = 2 * round(centre * frame_scale / 2)
            if rows:
                box = _people_box(rows, canvas_frame, w * sx, h * sy)
                if box is None:
                    i += 1
                    continue                              # nobody in view: nothing to classify
                l, t, side = int(box[0] / sx), int(box[1] / sy), int(box[2] / max(sx, sy))
                frames = [f[t:t + side, l:l + side] for _, f in buf]
            else:
                frames = [f for _, f in buf]
            out_rows.append({"frame": canvas_frame, "p": round(prob(frames), 3)})
        i += 1
    cap.release()
    tmp = out.with_suffix(".part")
    tmp.write_text("\n".join(json.dumps(r) for r in out_rows) + ("\n" if out_rows else ""), encoding="utf-8")
    tmp.replace(out)
    print(f"{video.stem}: {len(out_rows)} violence windows -> {out}", flush=True)


if __name__ == "__main__":
    {"clips": score_clips}[sys.argv[1]]()
