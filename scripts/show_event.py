"""Render an event's frame(s) with bag / owner / carrier boxes -> data/debug/<event_id>_<offset>.jpg

Usage: python scripts/show_event.py <event_id> [offsets_s ...]      e.g. cctv-G421-000055 -2 0 2 4
"""
import json
import pathlib
import sys

import cv2

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "backend"))
from argus.vision.common import DATA_DIR as DATA, FPS  # noqa: E402

eid = sys.argv[1]
offsets = [float(x) for x in sys.argv[2:]] or [-2, 0, 2, 4]
ev = next(json.loads(l) for l in (DATA / "events" / "cctv.jsonl").open() if json.loads(l)["event_id"] == eid)
clip, f0 = ev["media"]["clip"], ev["media"]["frame"]
want = {}
for key in ("owner", "carrier"):
    if ev["attrs"].get(key):
        want[int(ev["attrs"][key].split(":t")[1])] = key
tracks = {}
for l in (DATA / "tracks" / f"{clip}.jsonl").open():
    d = json.loads(l)
    if d["tid"] in want:
        tracks.setdefault(d["frame"], []).append(d)
bags = {}
bp = DATA / "tracks" / f"{clip}.bags.jsonl"
if bp.exists():
    for l in bp.open():
        d = json.loads(l)
        bags.setdefault(d["frame"], []).append(d)

cap = cv2.VideoCapture(str(DATA / "meva" / "video" / f"{clip}.avi"))
out = DATA / "debug"
out.mkdir(exist_ok=True)
for off in offsets:
    fr = int(f0 + off * FPS) // 2 * 2
    cap.set(cv2.CAP_PROP_POS_FRAMES, fr)
    ok, img = cap.read()
    if not ok:
        continue
    for d in tracks.get(fr, []):
        x1, y1, x2, y2 = map(int, d["xyxy"])
        col = (0, 200, 0) if want[d["tid"]] == "owner" else (0, 0, 255)
        cv2.rectangle(img, (x1, y1), (x2, y2), col, 3)
        cv2.putText(img, f"{want[d['tid']]} t{d['tid']}", (x1, y1 - 8), cv2.FONT_HERSHEY_SIMPLEX, 1.1, col, 3)
    for d in bags.get(fr, []):
        x1, y1, x2, y2 = map(int, d["xyxy"])
        cv2.rectangle(img, (x1, y1), (x2, y2), (0, 220, 255), 3)
    cv2.putText(img, f"{eid} {ev['type']} frame {fr} ({off:+.0f}s)", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 4)
    p = out / f"{eid}_{off:+.0f}.jpg"
    cv2.imwrite(str(p), cv2.resize(img, (960, 536)))
    print(p)
