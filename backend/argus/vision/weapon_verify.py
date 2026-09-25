"""Second opinion on weapon alerts: the detector proposes, a vision-language model verifies.

The weapon detector sees guns in phones, bottles and wallets on footage unlike its training cameras: it raised a
false weapon alert on 72 of 149 ordinary CCTV clips. Shown a close crop of each ALERT (not each frame), Gemini
removed 66 of those and all 4 false alerts on the unseen test camera, and kept 33 of 37 real weapon alerts
(eval/weapons_vlm.py, data/cache/weapons_vlm.json).

Policy: an alert is dropped only when the answer is a clear "no"; "yes" and "unsure" keep it. With no key or no
network the alert is kept and marked unverified, so the system is never less safe offline.
"""
from __future__ import annotations

import base64
import json
import os
import time

import cv2

SCHEMA = {"type": "OBJECT", "properties": {"weapon": {"type": "STRING", "enum": ["yes", "no", "unsure"]},
                                           "what": {"type": "STRING"}}, "required": ["weapon", "what"]}
PROMPT = ("A CCTV weapon detector drew the red box. Look at what is in the box and in the person's hands. Is a real "
          "handgun, rifle or knife clearly visible? Phones, bottles, cups, wallets, bags, remotes, tools, sticks and "
          "empty hands are NOT weapons. Answer yes, no, or unsure, and say in a few words what the object is.")


def crop(img, box):
    h, w = img.shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    img = img.copy()
    cv2.rectangle(img, (x1 - 3, y1 - 3), (x2 + 3, y2 + 3), (0, 0, 255), 2)
    side = min(max(256, 4 * max(x2 - x1, y2 - y1)), w, h)
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    l, t = max(0, min(w - side, cx - side // 2)), max(0, min(h - side, cy - side // 2))
    c = img[t:t + side, l:l + side]
    return cv2.resize(c, (512, 512 * c.shape[0] // max(c.shape[1], 1)))


def verify(img, box) -> dict | None:
    """{"weapon": yes|no|unsure, "what": ...}, or None when the model can't be reached."""
    from argus.agent import GEMINI_KEY, _post
    if not GEMINI_KEY or os.environ.get("ARGUS_LLM", "on").lower() == "off":
        return None
    ok, buf = cv2.imencode(".jpg", crop(img, box), [cv2.IMWRITE_JPEG_QUALITY, 90])
    body = {"contents": [{"role": "user", "parts": [
        {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(buf.tobytes()).decode()}},
        {"text": PROMPT}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA, "temperature": 0}}
    for _ in range(3):
        out = _post(body)
        if out is None:
            return None
        try:
            return json.loads(out["candidates"][0]["content"]["parts"][0]["text"])
        except Exception:
            time.sleep(2)
    return None


def filter_events(events: list[dict], grab) -> list[dict]:
    """Drop weapon_visible events the verifier says are not weapons. grab(frame, bbox) -> (image, bbox in its
    pixels) or (None, None). Other events pass through untouched."""
    out = []
    for e in events:
        if e["type"] != "weapon_visible":
            out.append(e)
            continue
        img, box = grab(e["media"].frame, e["media"].bbox)
        v = verify(img, box) if img is not None else None
        if v is None:
            e["attrs"]["verified"] = "unverified"
        else:
            e["attrs"]["verified"] = v["weapon"]
            e["attrs"]["verifier_saw"] = v.get("what", "")[:80]
            if v["weapon"] == "no":
                print(f"[weapons] alert dropped by the verifier: {v.get('what')}", flush=True)
                continue
        out.append(e)
    return out
