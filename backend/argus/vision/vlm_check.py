"""Experimental: a vision-language model as a second opinion on camera bag alerts. Not part of the live pipeline.

For every custody_change / abandoned_object event, Gemini sees three frames (3 s before, at, and 3 s after the
alert) with the rule's box drawn, is told what the rule claims, and answers supports / contradicts / unsure.
Each alert is labelled from the MEVA annotations (evaluation only): near a staged theft or abandonment on the same
camera, or not. The result says how often the second opinion keeps real alerts and removes false ones.

Usage:  python backend/argus/vision/vlm_check.py [events.jsonl video_dir ann_dir]   (default: the demo window)
Writes data/cache/vlm_check.json. Needs GEMINI_API_KEY; about 5 s per alert.
"""
import base64
import json
import os
import pathlib
import sys
import time

import cv2
import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from dotenv import load_dotenv  # noqa: E402

from argus import settings  # noqa: E402
from argus.config import site  # noqa: E402
from argus.ingest.groundtruth import load_ground_truth  # noqa: E402
from argus.vision.thumbs import crop_box  # noqa: E402

load_dotenv(settings.REPO_ROOT / ".env")
KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
MODEL = os.environ.get("ARGUS_GEMINI_MODEL", "gemini-flash-latest")
TYPES = ("custody_change", "abandoned_object")
OFFSETS_S = (-3.0, 0.0, 3.0)
RELATED_BEFORE_S = 120.0   # an unattended bag up to 2 min before a staged theft of it is part of that scenario

PROMPT = (
    "You are checking an automatic CCTV alert before it reaches a security guard. The three images are the same "
    "camera 3 seconds apart (before, at, after the alert); the coloured box marks what the rule flagged{carrier}. "
    "The rule claims: {claim} Look only at the images. verdict: 'supports' if the box really contains a portable "
    "object (bag, backpack, suitcase, laptop, phone) and the frames are consistent with the claim; 'contradicts' "
    "if the box holds no portable object (for example a plant, wall, chair, sign or shadow) or the frames clearly "
    "show something else; 'unsure' if you cannot tell. reason: one short sentence."
)
SCHEMA = {"type": "OBJECT", "properties": {"verdict": {"type": "STRING", "enum": ["supports", "contradicts", "unsure"]},
                                           "reason": {"type": "STRING"}}, "required": ["verdict", "reason"]}


def claim(e: dict) -> str:
    obj = e["attrs"].get("object", "object")
    if e["type"] == "abandoned_object":
        return f"a {obj} was left unattended and the person who brought it has walked away."
    return f"a {obj} that was resting or belonged to someone else was picked up and carried off by another person."


def frames(video: pathlib.Path, frame: int, bbox, fps: float) -> list[bytes]:
    cap = cv2.VideoCapture(str(video))
    out = []
    for off in OFFSETS_S:
        cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(frame + off * fps)))
        ok, img = cap.read()
        if not ok:
            continue
        l, t, r, b = crop_box(bbox, img.shape[1], img.shape[0], 5.0)
        crop = img[t:b, l:r].copy()
        cv2.rectangle(crop, (int(bbox[0] - l) - 4, int(bbox[1] - t) - 4), (int(bbox[2] - l) + 4, int(bbox[3] - t) + 4),
                      (40, 160, 245), 3)
        crop = cv2.resize(crop, (768, 432), interpolation=cv2.INTER_AREA)
        out.append(cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes())
    cap.release()
    return out


def ask(e: dict, jpgs: list[bytes]) -> dict:
    parts = [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(j).decode()}} for j in jpgs]
    parts.append({"text": PROMPT.format(claim=claim(e), carrier="")})
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA, "temperature": 0}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    r = httpx.post(url, json=body, headers={"x-goog-api-key": KEY}, timeout=60)
    r.raise_for_status()
    return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])


def label(e: dict, truth) -> str:
    for g in truth:
        if g.camera != e["sensor_id"]:
            continue
        if g.t_start - 60 <= e["t"] <= g.t_end + 60:
            return "staged"
        if g.kind == "theft" and g.t_start - RELATED_BEFORE_S <= e["t"] < g.t_start:
            return "staged"       # the bag was left unattended just before it was stolen: same scenario
    return "false"


def main(argv: list[str]) -> int:
    if not KEY:
        print("GEMINI_API_KEY is not set")
        return 1
    events_path = pathlib.Path(argv[0]) if argv else settings.EVENTS_DIR / "cctv.jsonl"
    video_dir = pathlib.Path(argv[1]) if len(argv) > 1 else settings.MEVA_DIR / "video"
    ann_dir = pathlib.Path(argv[2]) if len(argv) > 2 else settings.ANNOTATION_DIR
    cfg = site()
    truth = load_ground_truth(ann_dir, cfg)
    rows = []
    for e in (json.loads(x) for x in events_path.open(encoding="utf-8")):
        if e["type"] not in TYPES:
            continue
        jpgs = frames(video_dir / f"{e['media']['clip']}.avi", e["media"]["frame"], e["media"]["bbox"], cfg.fps)
        t0 = time.time()
        v = ask(e, jpgs)
        rows.append({"event_id": e["event_id"], "type": e["type"], "object": e["attrs"].get("object"),
                     "time": cfg.epoch_to_local(e["t"]), "label": label(e, truth), **v,
                     "seconds": round(time.time() - t0, 1)})
        r = rows[-1]
        print(f"{r['event_id']:<18} {r['type']:<17} {r['label']:<7} -> {r['verdict']:<11} {r['reason']}")
    staged = [r for r in rows if r["label"] == "staged"]
    false = [r for r in rows if r["label"] == "false"]
    summary = {
        "model": MODEL, "alerts": len(rows),
        "staged_kept": sum(r["verdict"] != "contradicts" for r in staged), "staged": len(staged),
        "false_removed": sum(r["verdict"] == "contradicts" for r in false), "false": len(false),
    }
    print(f"real alerts kept {summary['staged_kept']}/{summary['staged']}, "
          f"false alerts removed {summary['false_removed']}/{summary['false']}  ({MODEL})")
    out = settings.CACHE_DIR / "vlm_check.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
