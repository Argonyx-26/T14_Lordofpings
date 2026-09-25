"""Detector proposes, a vision-language model verifies: every weapon ALERT from the detector (3 of 6 frames at
conf >= 0.5) is shown to Gemini as a close crop, which answers whether a real gun or knife is visible.

Scored on the same two tests as weapons_public.py: the unseen camera Cam7 (84 real weapon appearances, 29 min) and
the 149 held-out ordinary clips (no weapons). An alert is dropped only when the answer is "no".

Usage (from backend/):  python -m argus.eval.weapons_vlm [weights]   -> data/cache/weapons_vlm.json
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import cv2

from argus import settings
from argus.vision import train_weapons as tw, weapon_verify

CONF, WIN, HITS = 0.5, 6, 3


def verify(img, box) -> dict:
    return weapon_verify.verify(img, box) or {"weapon": "unsure", "what": "no answer"}


def first_alert(frames):
    """frames: [(img_or_path, [(conf, box)])] in time order -> (index, box) of the first alert, or None."""
    hits = [bool(d) for _, d in frames]
    for i in range(len(hits) - WIN + 1 if len(hits) >= WIN else 1):
        w = range(i, min(i + WIN, len(hits)))
        if sum(hits[j] for j in w) >= HITS:
            j = max((j for j in w if hits[j]), key=lambda j: max(c for c, _ in frames[j][1]))
            return j, max(frames[j][1])[1]
    return None


def main(argv) -> int:
    from ultralytics import YOLO
    m = YOLO(str(Path(argv[0]) if argv else tw.WEIGHTS_V2))
    rows = []
    # Cam7: sequences of 2 fps frames; one alert per real appearance, and each false 6-frame window
    imgs = sorted((tw.OUT / "images" / "test").glob("*.jpg"))
    seqs = defaultdict(list)
    for i in range(0, len(imgs), 16):
        batch = imgs[i:i + 16]
        for p, r in zip(batch, m.predict([str(x) for x in batch], imgsz=tw.IMGSZ, conf=CONF, half=True, verbose=False)):
            seg, n = re.match(r"(.*)_frame_(\d+)$", p.stem).groups()
            gt = bool((tw.OUT / "labels" / "test" / f"{p.stem}.txt").read_text(encoding="utf-8").strip())
            seqs[seg].append((int(n), p, [(float(c), b) for c, b in zip(r.boxes.conf.tolist(), r.boxes.xyxy.tolist())], gt))
    for seg, fr in seqs.items():
        fr.sort(key=lambda x: x[0])
        k = 0
        while k + WIN <= len(fr):
            w = fr[k:k + WIN]
            if sum(bool(x[2]) for x in w) >= HITS:
                j = max((x for x in w if x[2]), key=lambda x: max(c for c, _ in x[2]))
                real = any(x[3] for x in fr[max(0, k - 5):k + WIN + 5])
                v = verify(cv2.imread(str(j[1])), max(j[2])[1])
                rows.append({"set": "cam7", "real": real, "item": f"{seg}@{j[0]}", **v})
                print(f"cam7 {'REAL ' if real else 'false'} -> {v['weapon']:<6} {v['what']}", flush=True)
                k += WIN + 6                       # one check per alert, as the rule's refractory would
                continue
            k += 1
    _, test = tw.neg_split()
    for clip in test:
        frames = []
        cap = cv2.VideoCapture(str(clip))
        n = 0
        while True:
            ok, img = cap.read()
            if not ok:
                break
            if n % 2 == 0:
                r = m.predict(img, imgsz=tw.IMGSZ, conf=CONF, half=True, verbose=False)[0]
                frames.append((img, [(float(c), b) for c, b in zip(r.boxes.conf.tolist(), r.boxes.xyxy.tolist())]))
            n += 1
        cap.release()
        a = first_alert(frames)
        if a:
            v = verify(frames[a[0]][0], a[1])
            rows.append({"set": "ordinary", "real": False, "item": clip.stem, **v})
            print(f"ordinary {clip.stem} -> {v['weapon']:<6} {v['what']}", flush=True)
    cam_real = [r for r in rows if r["set"] == "cam7" and r["real"]]
    cam_false = [r for r in rows if r["set"] == "cam7" and not r["real"]]
    ordn = [r for r in rows if r["set"] == "ordinary"]
    s = {"detector": m.ckpt_path if hasattr(m, "ckpt_path") else str(argv[:1]),
         "cam7_real_alerts_kept": f"{sum(r['weapon'] != 'no' for r in cam_real)}/{len(cam_real)}",
         "cam7_false_alerts_kept": f"{sum(r['weapon'] != 'no' for r in cam_false)}/{len(cam_false)}",
         "ordinary_false_alerts_kept": f"{sum(r['weapon'] != 'no' for r in ordn)}/{len(ordn)} (of {len(test)} clips)",
         "answers": {k: dict(__import__('collections').Counter(r['weapon'] for r in v))
                     for k, v in (("cam7_real", cam_real), ("cam7_false", cam_false), ("ordinary", ordn))}}
    (settings.CACHE_DIR / "weapons_vlm.json").write_text(json.dumps({"summary": s, "rows": rows}, indent=1), encoding="utf-8")
    print(json.dumps(s, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
