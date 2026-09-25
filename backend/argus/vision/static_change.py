"""Class-agnostic static-change detector (no training): finds regions where an object was REMOVED
or APPEARED and the scene stayed that way. -> data/tracks/<stem>.changes.jsonl

Dual background model: B_long = median of 1 fps samples 30-60 s ago, B_short = median of the last
5 s. Moving people vanish from both medians; a purse lifted off a bench does not. Pixels covered by
people (from the cached YOLO tracks) are masked out, so people sitting down or standing up are not
reported as objects. appeared vs removed: whichever background has more texture in the region.

EXPERIMENTAL - not used by rules.py. It does find the G331 theft-3 purse removal (dark-on-dark, via
the structure channel), but the thief had stood beside the purse for ~2 min, so from video alone the
removal looks like someone leaving with their own bag; a rule on it caught no theft and added 12
false alarms, so it stays off.

Usage: python backend/argus/vision/static_change.py [clip.avi ...]   (default: all clips)
"""
from __future__ import annotations

import json
import pathlib
import sys
from collections import defaultdict

import cv2
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from argus.vision.common import FPS, MEVA_DIR, TRACKS_DIR  # noqa: E402

W, H = 480, 268                 # working resolution (1/4 of 1920x1072)
SX, SY = 1920 / W, 1072 / H
LONG = (60, 30)                 # seconds back: long background window
SHORT = 5                       # seconds: short background window
DIFF_T = 28                     # per-pixel colour difference threshold (0-255)
MIN_AREA, MAX_AREA = 60, 3500   # blob area in working pixels (~0.05% .. 2.7% of the frame)
PERSIST = 3                     # blob must be present in this many consecutive 1 s samples
PERSON_PAD = 0.12


def person_boxes(track_path: pathlib.Path) -> dict[int, list]:
    by_sec = defaultdict(list)
    with track_path.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d["cls"] == 0 and d["frame"] % 30 == 0:
                by_sec[d["frame"] // 30].append(d["xyxy"])
    return by_sec


def mask_people(boxes: list, mask: np.ndarray, pad: float = PERSON_PAD) -> None:
    for x1, y1, x2, y2 in boxes:
        pw, ph = (x2 - x1) * pad, (y2 - y1) * pad
        cv2.rectangle(mask, (int((x1 - pw) / SX), int((y1 - ph) / SY)), (int((x2 + pw) / SX), int((y2 + ph) / SY)), 1, -1)


NCC_T, NCC_MIN_STD, NCC_WIN = 0.3, 5.0, 9


def structure_change(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Pixels whose local window (NCC_WIN px) correlates poorly between two images, where there is
    texture to compare. Box-filter formulation, so it is one pass over the frame."""
    ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(np.float32)
    k = (NCC_WIN, NCC_WIN)
    ma, mb = cv2.blur(ga, k), cv2.blur(gb, k)
    va = cv2.blur(ga * ga, k) - ma * ma
    vb = cv2.blur(gb * gb, k) - mb * mb
    cov = cv2.blur(ga * gb, k) - ma * mb
    ncc = cov / np.sqrt(np.maximum(va, 1e-3) * np.maximum(vb, 1e-3))
    textured = np.sqrt(np.maximum(np.maximum(va, vb), 0)) > NCC_MIN_STD
    return ((ncc < NCC_T) & textured).astype(np.uint8)


def texture(img: np.ndarray, box) -> float:
    x1, y1, x2, y2 = box
    g = cv2.cvtColor(img[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(g, cv2.CV_32F).var()) if g.size else 0.0


def run(clip: pathlib.Path, out: pathlib.Path) -> int:
    people = person_boxes(TRACKS_DIR / f"{clip.stem}.jsonl")
    cap = cv2.VideoCapture(str(clip))
    samples: list[np.ndarray] = []
    f = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if f % int(FPS) == 0:
            _, img = cap.retrieve()
            samples.append(cv2.GaussianBlur(cv2.resize(img, (W, H), interpolation=cv2.INTER_AREA), (5, 5), 0))
        f += 1
    cap.release()

    active: list[dict] = []   # blobs being followed
    found: list[dict] = []
    for t in range(LONG[0], len(samples)):
        b_long = np.median(np.stack(samples[t - LONG[0]:t - LONG[1] + 1]), axis=0).astype(np.uint8)
        b_short = np.median(np.stack(samples[t - SHORT + 1:t + 1]), axis=0).astype(np.uint8)
        diff = cv2.absdiff(b_short, b_long).max(axis=2)
        m = (diff > DIFF_T).astype(np.uint8)
        # dark-on-dark objects (black purse on a black bench) barely change colour but do change local
        # STRUCTURE: low normalised cross-correlation between the two backgrounds
        m |= structure_change(b_long, b_short)
        pm = np.zeros((H, W), np.uint8)
        for s in range(t - SHORT + 1, t + 1):                 # anyone in the short window
            mask_people(people.get(s, []), pm)
        long_counts = np.zeros((H, W), np.float32)            # anyone who sat in the long window
        for s in range(t - LONG[0], t - LONG[1] + 1):
            tmp = np.zeros((H, W), np.uint8)
            mask_people(people.get(s, []), tmp, pad=0.0)  # tight: an object right beside them must survive
            long_counts += tmp
        pm |= (long_counts > 0.5 * (LONG[0] - LONG[1])).astype(np.uint8)
        m[pm > 0] = 0
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        n, lab, stats, _ = cv2.connectedComponentsWithStats(m)
        blobs = [tuple(int(v) for v in stats[i, :4]) for i in range(1, n) if MIN_AREA <= stats[i, 4] <= MAX_AREA]
        nxt = []
        for x, y, w, h in blobs:
            box = (x, y, x + w, y + h)
            match = None
            for a in active:
                bx = a["box"]
                ix = max(0, min(bx[2], box[2]) - max(bx[0], box[0]))
                iy = max(0, min(bx[3], box[3]) - max(bx[1], box[1]))
                if ix * iy > 0.3 * min(w * h, (bx[2] - bx[0]) * (bx[3] - bx[1])):
                    match = a
                    break
            if match:
                match.update(box=box, last=t, n=match["n"] + 1)
                if match["n"] == PERSIST and not match.get("emitted"):
                    match["emitted"] = True
                    tl, ts = texture(b_long, box), texture(b_short, box)
                    found.append({"frame": match["first"] * int(FPS), "confirm_frame": t * int(FPS),
                                  "kind": "removed" if tl > ts else "appeared",
                                  "xyxy": [round(box[0] * SX), round(box[1] * SY), round(box[2] * SX), round(box[3] * SY)],
                                  "area": w * h, "texture_long": round(tl, 1), "texture_short": round(ts, 1),
                                  "diff": round(float(diff[y:y + h, x:x + w].mean()), 1)})
                nxt.append(match)
            else:
                nxt.append({"box": box, "first": t, "last": t, "n": 1})
        active = [a for a in nxt if t - a["last"] <= 1]
    with out.open("w", encoding="utf-8") as fo:
        for c in found:
            fo.write(json.dumps(c) + "\n")
    return len(found)


if __name__ == "__main__":
    clips = [pathlib.Path(p) for p in sys.argv[1:]] or sorted((MEVA_DIR / "video").glob("*.avi"))
    for clip in clips:
        if clip.stem.endswith("G474") or not (TRACKS_DIR / f"{clip.stem}.jsonl").exists():
            continue
        out = TRACKS_DIR / f"{clip.stem}.changes.jsonl"
        n = run(clip, out)
        print(f"{clip.stem}: {n} static changes -> {out.name}", flush=True)
