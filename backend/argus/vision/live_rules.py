"""Unattended bag, live: the abandoned-object rule on a streaming camera (webcam on stage), frame by frame.

The offline rule (rules.py) looks at a whole clip; this one only has the past. Per bag:
  1. a bag is a SPOT: its box followed across frames (IoU), kept through short detection gaps
  2. it counts as RESTING once its centre has moved less than REST_DRIFT bag-heights for REST_S seconds
  3. its OWNER is the person who brought it (nearest when it appeared or last moved), else the nearest at rest
  4. it is UNATTENDED while its owner is not within NEAR person-heights of it (bystanders don't count: a crowded
     platform always has someone next to a bag; with no owner, anyone near attends it); after ABANDON_S seconds it fires
     abandoned_object: severity 0.8 if the owner has left the frame (decisive: the incident opens at once),
     0.7 if they are merely away (decisive only in the airport profile)
The overlay draws each bag's state and countdown, so the audience can watch it happen.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

BAGS = {24: "backpack", 26: "handbag", 28: "suitcase"}
PERSON = 0
REST_S, REST_DRIFT = 2.0, 0.6
NEAR = 1.2                       # person-heights between the bag and the nearest person's box
ABANDON_S = 15.0
LOST_S = 3.0                     # a bag unseen this long is forgotten (picked up, or never really there)
IOU_MATCH = 0.2


def _iou(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0]); h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    i = w * h
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i)


def _gap(box, person) -> float:
    """Distance between a bag box and a person box, in that person's heights (0 when they overlap)."""
    dx = max(person[0] - box[2], box[0] - person[2], 0)
    dy = max(person[1] - box[3], box[1] - person[3], 0)
    return (dx * dx + dy * dy) ** 0.5 / max(person[3] - person[1], 1)


@dataclass
class Spot:
    sid: int
    kind: str
    box: list
    first: float
    seen: float
    anchor: tuple = (0.0, 0.0)
    anchor_t: float = 0.0
    rest_since: float | None = None
    owner: int | None = None
    carrier: int | None = None       # nearest person while the bag was arriving or moving: who brought it
    alone_since: float | None = None
    fired: bool = False
    history: list = field(default_factory=list)


class LiveBagRule:
    def __init__(self, abandon_s: float = ABANDON_S, on_event=None):
        self.abandon_s, self.on_event = abandon_s, on_event
        self.spots: dict[int, Spot] = {}
        self._next = 1

    def update(self, dets: list[tuple[int, int | None, float, list]], now: float | None = None, frame=None) -> None:
        """dets: (cls, track id, conf, xyxy) for this frame."""
        now = time.monotonic() if now is None else now
        people = {tid: box for cls, tid, _, box in dets if cls == PERSON and tid is not None}
        bags = [(cls, box) for cls, _, _, box in dets if cls in BAGS]
        for cls, box in bags:
            s = max(self.spots.values(), key=lambda s: _iou(s.box, box), default=None)
            if s is None or _iou(s.box, box) < IOU_MATCH:
                s = Spot(self._next, BAGS[cls], box, now, now, ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), now)
                self.spots[s.sid] = s
                self._next += 1
            s.box, s.seen = box, now
            moving = s.first == now
            cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            h = max(box[3] - box[1], 8)
            if abs(cx - s.anchor[0]) + abs(cy - s.anchor[1]) > REST_DRIFT * h:     # moved: carried, not resting
                s.anchor, s.anchor_t, s.rest_since, s.owner, s.alone_since, s.fired = (cx, cy), now, None, None, None, False
                moving = True
            elif s.rest_since is None and now - s.anchor_t >= REST_S:
                s.rest_since = now
                near = min(people.items(), key=lambda kv: _gap(box, kv[1]), default=None)
                s.owner = s.carrier if s.carrier is not None else (
                    near[0] if near and _gap(box, near[1]) < 2 * NEAR else None)
            if moving:
                near = min(people.items(), key=lambda kv: _gap(box, kv[1]), default=None)
                s.carrier = near[0] if near and _gap(box, near[1]) < NEAR else None
        for sid in [k for k, s in self.spots.items() if now - s.seen > LOST_S]:
            del self.spots[sid]
        for s in self.spots.values():
            if s.rest_since is None:
                continue
            if s.owner is not None:          # a bag is left when its OWNER goes; bystanders in a crowd don't count
                attended = s.owner in people and _gap(s.box, people[s.owner]) < NEAR
            else:                            # nobody was next to it when it came to rest: anyone near attends it
                attended = any(_gap(s.box, p) < NEAR for p in people.values())
            if attended:
                s.alone_since = None
                continue
            s.alone_since = s.alone_since or now
            if not s.fired and now - s.alone_since >= self.abandon_s:
                s.fired = True
                owner_left = s.owner is None or s.owner not in people
                if self.on_event:
                    self.on_event(s, owner_left, now - s.alone_since, frame)

    def overlay(self, img, scale: float, now: float | None = None):
        import cv2
        now = time.monotonic() if now is None else now
        for s in self.spots.values():
            x1, y1, x2, y2 = (int(v * scale) for v in s.box)
            if s.fired:
                col, text = (40, 40, 235), f"UNATTENDED {s.kind} - alert sent"
            elif s.alone_since is not None:
                left = max(0.0, self.abandon_s - (now - s.alone_since))
                col, text = (0, 165, 255), f"{s.kind} alone - alert in {left:4.1f} s"
            elif s.rest_since is not None:
                col, text = (80, 220, 120), f"{s.kind} put down - owner nearby"
            else:
                continue
            cv2.rectangle(img, (x1, y1), (x2, y2), col, 3)
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            cv2.rectangle(img, (x1, max(0, y1 - th - 10)), (x1 + tw + 8, y1), col, -1)
            cv2.putText(img, text, (x1 + 4, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
        return img
