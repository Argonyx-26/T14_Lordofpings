"""Evidence thumbnails: one still per CCTV event, cropped around what the rule saw, with its box drawn.

The console shows them next to each piece of evidence (served by the backend at /media/thumbs/<event_id>.jpg),
so an operator sees the bag, the carrier or the runner before replaying the moment.

Usage (after rules.py):  python backend/argus/vision/thumbs.py        # data/events/cctv.jsonl -> data/meva/web/thumbs/
"""
import json
import pathlib
import shutil
import sys
from collections import defaultdict

import cv2

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from argus.settings import EVENTS_DIR, MEVA_DIR, TRACKS_DIR, WEB_VIDEO_DIR  # noqa: E402

OUT_DIR = WEB_VIDEO_DIR / "thumbs"
THUMB_W, THUMB_H = 480, 270          # 16:9, sharp at the console's size on a retina screen
MIN_CROP_H, CONTEXT = 360, 4.0       # crop at least 360 px tall, about 4x the object so the scene reads
SKIP = {"occupancy"}                 # head counts have no single object to show
COLOR = {"custody_change": (60, 60, 235), "abandoned_object": (40, 160, 245), "running": (235, 180, 60)}
DEFAULT_COLOR = (210, 210, 210)


def crop_box(bbox, frame_w: int, frame_h: int, context: float = CONTEXT) -> tuple[int, int, int, int]:
    """A 16:9 window centred on the box, big enough for context, kept inside the frame."""
    x1, y1, x2, y2 = bbox
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    h = min(frame_h, max(MIN_CROP_H, context * max(y2 - y1, (x2 - x1) * 9 / 16)))
    w = min(frame_w, h * 16 / 9)
    h = w * 9 / 16
    left = min(max(0, cx - w / 2), frame_w - w)
    top = min(max(0, cy - h / 2), frame_h - h)
    return int(left), int(top), int(left + w), int(top + h)


def render(img, bbox, etype: str, person=None):
    """person: the carrier's box for a custody change, drawn thinner so the object stays the focus."""
    fh, fw = img.shape[:2]
    both = bbox if person is None else [min(bbox[0], person[0]), min(bbox[1], person[1]),
                                        max(bbox[2], person[2]), max(bbox[3], person[3])]
    l, t, r, b = crop_box(both, fw, fh, CONTEXT if person is None else 1.4)
    crop = img[t:b, l:r].copy()
    s = THUMB_W / crop.shape[1]
    crop = cv2.resize(crop, (THUMB_W, THUMB_H), interpolation=cv2.INTER_AREA)

    def box(bb, color, width, pad):
        x1, y1, x2, y2 = ((bb[0] - l) * s, (bb[1] - t) * s, (bb[2] - l) * s, (bb[3] - t) * s)
        cv2.rectangle(crop, (int(x1) - pad, int(y1) - pad), (int(x2) + pad, int(y2) + pad), color, width, cv2.LINE_AA)

    if person is not None:
        box(person, (255, 255, 255), 1, 2)
    box(bbox, COLOR.get(etype, DEFAULT_COLOR), 2, 4)
    return crop


def person_boxes(tracks: pathlib.Path, wanted: set[tuple[int, int]]) -> dict[tuple[int, int], list[float]]:
    """(tid, frame) -> xyxy from a track file, for the carriers of custody changes (nearest frame within 4)."""
    rows: dict[int, list[tuple[int, list[float]]]] = defaultdict(list)
    tids = {tid for tid, _ in wanted}
    if not tids or not tracks.exists():
        return {}
    with tracks.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["tid"] in tids:
                rows[r["tid"]].append((r["frame"], r["xyxy"]))
    out = {}
    for tid, frame in wanted:
        near = min(rows.get(tid, []), key=lambda fr: abs(fr[0] - frame), default=None)
        if near and abs(near[0] - frame) <= 4:
            out[(tid, frame)] = near[1]
    return out


def carrier_tid(e: dict) -> int | None:
    c = (e.get("attrs") or {}).get("carrier") or ""
    return int(c.split(":t")[1]) if e["type"] == "custody_change" and ":t" in c else None


def make_thumbs(events: list[dict], video_for, out_dir: pathlib.Path = OUT_DIR, tracks_for=None) -> int:
    """events: Event dicts with media {clip, frame, bbox}; video_for(clip) -> video path; tracks_for(clip) -> the
    clip's track file (to outline a custody change's carrier). Returns the number of thumbnails written."""
    by_clip: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        m = e.get("media") or {}
        bbox = m.get("bbox")
        if e["type"] in SKIP or not bbox or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
            continue
        by_clip[m["clip"]].append(e)
    out_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for clip, evs in by_clip.items():
        path = video_for(clip)
        if path is None or not path.exists():
            continue
        wanted = {(carrier_tid(e), e["media"]["frame"]) for e in evs if carrier_tid(e) is not None}
        carriers = person_boxes(tracks_for(clip), wanted) if tracks_for and wanted else {}
        cap = cv2.VideoCapture(str(path))
        frame_no, img = -1, None
        for e in sorted(evs, key=lambda e: e["media"]["frame"]):  # read forward once: seeking an AVI is slow
            target = e["media"]["frame"]
            while frame_no < target:
                ok = cap.grab()
                if not ok:
                    break
                frame_no += 1
                if frame_no == target:
                    ok, img = cap.retrieve()
            if frame_no != target or img is None:
                continue
            cv2.imwrite(str(out_dir / f"{e['event_id']}.jpg"), render(img, e["media"]["bbox"], e["type"],
                                                                     carriers.get((carrier_tid(e), target))),
                        [cv2.IMWRITE_JPEG_QUALITY, 82])
            n += 1
        cap.release()
    return n


def main() -> int:
    events = [json.loads(line) for line in (EVENTS_DIR / "cctv.jsonl").open(encoding="utf-8")]
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)       # event ids are renumbered whenever rules.py runs
    n = make_thumbs(events, lambda clip: MEVA_DIR / "video" / f"{clip}.avi",
                    tracks_for=lambda clip: TRACKS_DIR / f"{clip}.jsonl")
    print(f"wrote {n} evidence thumbnails -> {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
