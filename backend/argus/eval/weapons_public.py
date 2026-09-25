"""Public pretrained weapon detectors against ours, on our two tests (same alert rule for all: a weapon class at
conf >= CONF on 3 of 6 consecutive analysed frames):
  real weapons   the unseen camera Cam7 (84 weapon appearances, 29 min, 2 fps), like train_weapons.py alerts()
  false alarms   the 149 held-out fight-dataset clips (ordinary CCTV, no weapons; recordings never used by v3)

Usage (from backend/):  python -m argus.eval.weapons_public [weights.pt ...]   -> data/cache/weapons_public.json
"""
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

from argus import settings
from argus.vision import train_weapons as tw

WEAPON = re.compile(r"gun|pistol|rifle|knife|firearm|weapon|revolver|shotgun|handgun|sniper|smg|ak|m4", re.I)
CONF, WIN, HITS = 0.5, 6, 3


class Both:
    """Two detectors must agree: a frame counts only if both see a weapon and their boxes overlap."""

    def __init__(self, a, b, conf_b=0.25):
        self.a, self.b, self.conf_b = a, b, conf_b
        self.ca, self.cb = weapon_classes(a), weapon_classes(b)
        self.names = {0: "weapon (both agree)"}

    def predict(self, source, stream=False, imgsz=960, conf=0.5, classes=None, vid_stride=1, half=True, verbose=False):
        ra = self.a.predict(source, stream=False, imgsz=imgsz, conf=conf, classes=self.ca, vid_stride=vid_stride,
                            half=half, verbose=False)
        rb = self.b.predict(source, stream=False, imgsz=imgsz, conf=self.conf_b, classes=self.cb,
                            vid_stride=vid_stride, half=half, verbose=False)
        return [_Agree(x, y) for x, y in zip(ra, rb)]


class _Agree:
    def __init__(self, x, y):
        bx, by = x.boxes.xyxy.tolist(), y.boxes.xyxy.tolist()
        self.boxes = [a for a in bx if any(min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])
                                           for b in by)]


def weapon_classes(model) -> list[int]:
    return [i for i, n in model.names.items() if WEAPON.search(str(n)) and n.lower() not in ("person", "no_weapon")]


def cam7(model, classes) -> dict:
    imgs = sorted((tw.OUT / "images" / "test").glob("*.jpg"))
    seqs = defaultdict(list)
    for i in range(0, len(imgs), 16):
        batch = imgs[i:i + 16]
        for p, r in zip(batch, model.predict([str(x) for x in batch], imgsz=tw.IMGSZ, conf=CONF, classes=classes,
                                             half=True, verbose=False)):
            seg, n = re.match(r"(.*)_frame_(\d+)$", p.stem).groups()
            gt = bool((tw.OUT / "labels" / "test" / f"{p.stem}.txt").read_text(encoding="utf-8").strip())
            seqs[seg].append((int(n), len(r.boxes) > 0, gt))
    ep = found = fa = 0
    for fr in seqs.values():
        fr.sort()
        run = []
        for k, (_, _, gt) in enumerate(fr):
            if gt:
                run.append(k)
            if (not gt or k == len(fr) - 1) and run:
                ep += 1
                found += any(sum(x[1] for x in fr[j:j + WIN]) >= HITS for j in range(max(0, run[0] - 5), run[-1] + 1))
                run = []
        k = 0
        while k + WIN <= len(fr):
            w = fr[k:k + WIN]
            if not any(x[2] for x in w) and sum(x[1] for x in w) >= HITS:
                fa, k = fa + 1, k + WIN
                continue
            k += 1
    return {"appearances": ep, "alerted": found, "false_alerts_29min": fa}


def ordinary(model, classes) -> dict:
    _, test = tw.neg_split()
    flagged = 0
    for clip in test:
        hits = [len(r.boxes) > 0 for r in model.predict(str(clip), stream=True, imgsz=tw.IMGSZ, conf=CONF,
                                                        classes=classes, vid_stride=2, half=True, verbose=False)]
        flagged += any(sum(hits[i:i + WIN]) >= HITS for i in range(max(1, len(hits) - WIN + 1)))
    return {"clips": len(test), "clips_false_alert": flagged}


def main(argv) -> int:
    from ultralytics import YOLO
    pub = sorted((settings.REPO_ROOT / "models" / "public").glob("*best.pt"))
    cands = [Path(a) if "+" not in a else Path(a) for a in argv] or [tw.WEIGHTS, tw.WEIGHTS_V2, settings.REPO_ROOT / "models" / "gun-knife-yolo11n.pt", *pub]
    out_path = settings.CACHE_DIR / "weapons_public.json"
    out = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    for w in cands:
        t0 = time.time()
        if "+" in w.name:
            a, b = str(w).split("+")
            m = Both(YOLO(a), YOLO(str(Path(a).parent / b) if not Path(b).exists() else b))
            cls = [0]
        else:
            m = YOLO(str(w))
            cls = weapon_classes(m)
        row = {"classes": {i: m.names[i] for i in cls}}
        if not cls:
            row["error"] = "no weapon classes"
        else:
            row.update(cam7=cam7(m, cls), ordinary=ordinary(m, cls))
        out[w.name] = row
        out_path.write_text(json.dumps(out, indent=1), encoding="utf-8")
        c, o = row.get("cam7", {}), row.get("ordinary", {})
        print(f"{w.name:<48} real {c.get('alerted')}/{c.get('appearances')}  false/29min {c.get('false_alerts_29min')}  "
              f"ordinary clips flagged {o.get('clips_false_alert')}/{o.get('clips')}  {list(row['classes'].values())} "
              f"({time.time() - t0:.0f} s)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
