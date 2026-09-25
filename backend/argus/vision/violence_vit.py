"""Appearance evidence for violence: a pretrained ViT violence classifier scored on sampled frames.

Model: jaranohaal/vit-base-violence-detection (Apache-2.0; ViT-B/16 fine-tuned on the Real Life Violence Situations
dataset, a different dataset from the surveillance clips we test on). Weights in models/vit-violence/.

It sees what a fight looks like; the pose features (violence.py) see how bodies move. violence.py fuses both.

Usage (repo root):  python backend/argus/vision/violence_vit.py clips   # score the 300 fight-dataset clips (cache)
"""
import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODEL_DIR = ROOT / "models" / "vit-violence"
CACHE = ROOT / "data" / "train" / "fights_vit.json"
FEATURES = ["vit_mean", "vit_max", "vit_p75"]

_m = None


def available() -> bool:
    return (MODEL_DIR / "model.safetensors").exists()


def _model():
    global _m
    if _m is None:
        import torch
        from transformers import ViTForImageClassification, ViTImageProcessor
        proc = ViTImageProcessor.from_pretrained(MODEL_DIR)
        model = ViTForImageClassification.from_pretrained(MODEL_DIR).eval()
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        model.to(dev)
        # The card gives no label names; its training set's classes are NonViolence / Violence, which the standard
        # loaders index alphabetically: 1 = violent. Fixed before scoring anything.
        violent = 1
        _m = (proc, model, dev, violent)
    return _m


def probs(frames_bgr: list) -> list[float]:
    """P(violent) for each BGR frame."""
    import torch
    if not frames_bgr:
        return []
    proc, model, dev, violent = _model()
    out = []
    for i in range(0, len(frames_bgr), 32):
        batch = [np.ascontiguousarray(f[:, :, ::-1]) for f in frames_bgr[i:i + 32]]
        inputs = proc(images=batch, return_tensors="pt").to(dev)
        with torch.no_grad():
            p = model(**inputs).logits.softmax(-1)[:, violent]
        out += p.float().cpu().tolist()
    return out


def summarise(p: list[float]) -> dict[str, float]:
    return {"vit_mean": float(np.mean(p)) if p else 0.0, "vit_max": float(np.max(p)) if p else 0.0,
            "vit_p75": float(np.percentile(p, 75)) if p else 0.0}


def sample_frames(video: pathlib.Path, every: int = 5, limit: int = 16) -> list:
    import cv2
    cap, frames, i = cv2.VideoCapture(str(video)), [], 0
    while len(frames) < limit:
        ok = cap.grab()
        if not ok:
            break
        if i % every == 0:
            frames.append(cap.retrieve()[1])
        i += 1
    cap.release()
    return frames


def score_clips() -> dict:
    fights = ROOT / "data" / "train" / "fights"
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    for folder in ("fight", "noFight"):
        for clip in sorted((fights / folder).glob("*")):
            if clip.stem not in cache:
                cache[clip.stem] = probs(sample_frames(clip))
    CACHE.write_text(json.dumps(cache), encoding="utf-8")
    print(f"{len(cache)} clips scored -> {CACHE}")
    return cache


if __name__ == "__main__":
    {"clips": score_clips}[sys.argv[1]]()
