"""Video door-contact sensor (no training): motion of the upper DOOR LEAF, above head height.

A person walking past a door does not change the top of the door panel; the door swinging open does.
Per door we track the mean absolute difference between the leaf region and a rolling median
background (last ~10 s), then take the rising edges of that signal as door-open events.

  python backend/argus/vision/door_sensor.py [clip.avi ...]      -> data/tracks/<stem>.doors.npz (signals)

rules.py turns the cached signals into door_activity events (see door_events()).
"""
from __future__ import annotations

import pathlib
import sys

import cv2
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from argus.vision.common import FPS, MEVA_DIR, TRACKS_DIR, camera_cfg, clip_info  # noqa: E402

STEP = 3            # sample every 3rd frame (10 Hz)
BG_SAMPLES = 100    # background = median over the last 10 s ...
BG_STRIDE = 5       # ... using every 5th sample

# event extraction (tuned once, global for all cameras)
K_MAD = 6.0         # threshold = median + K_MAD * MAD + FLOOR
FLOOR = 2.0
REFRACTORY_S = 5.0  # one opening per door per 5 s (a door stays open while a group walks through)
LAG_S = 1.5         # the leaf visibly moves ~1.5 s after the annotated "opens door" start


def signals(clip: pathlib.Path, leaves: dict) -> tuple[np.ndarray, dict]:
    cap = cv2.VideoCapture(str(clip))
    hist = {k: [] for k in leaves}
    sig = {k: [] for k in leaves}
    times = []
    f = 0
    while True:
        if not cap.grab():
            break
        if f % STEP == 0:
            _, img = cap.retrieve()
            times.append(f)
            for k, (x1, y1, x2, y2) in leaves.items():
                g = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY).astype(np.float32)
                h = hist[k]
                h.append(g)
                if len(h) > BG_SAMPLES:
                    h.pop(0)
                bg = np.median(np.stack(h[::BG_STRIDE]), axis=0) if len(h) >= 20 else g
                sig[k].append(float(np.abs(g - bg).mean()))
        f += 1
    cap.release()
    return np.array(times), {k: np.array(v, np.float32) for k, v in sig.items()}


def door_events(frames: np.ndarray, sig: dict) -> list[tuple[str, int, float]]:
    """-> [(door, frame, strength)] rising edges above a robust per-door threshold."""
    out = []
    for door, v in sig.items():
        if len(v) < 30:
            continue
        med = float(np.median(v))
        thr = med + K_MAD * float(np.median(np.abs(v - med))) + FLOOR
        last = -1e9
        above = v > thr
        for i in range(1, len(v)):
            if above[i] and not above[i - 1] and frames[i] - last > REFRACTORY_S * FPS:
                peak = float(v[i:i + 20].max())
                out.append((door, max(0, int(frames[i] - LAG_S * FPS)), round((peak - med) / max(thr - med, 1e-3), 2)))
                last = frames[i]
    return sorted(out, key=lambda e: e[1])


if __name__ == "__main__":
    clips = [pathlib.Path(p) for p in sys.argv[1:]] or sorted((MEVA_DIR / "video").glob("*.avi"))
    for clip in clips:
        leaves = camera_cfg(clip_info(clip.stem).camera).get("door_leaf") or {}
        out = TRACKS_DIR / f"{clip.stem}.doors.npz"
        if not leaves or out.exists():
            continue
        frames, sig = signals(clip, leaves)
        np.savez(out, frames=frames, **sig)
        print(f"{clip.stem}: {len(door_events(frames, sig))} door-leaf events from {list(leaves)}", flush=True)
