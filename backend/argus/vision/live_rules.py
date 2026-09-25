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
from collections import deque
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


# --- threats on the live camera ----------------------------------------------------------------------------------
SHARP = {43: "knife", 76: "scissors"}         # COCO classes: reliable up close, useless at CCTV range (0/24 frames
SHARP_CONF, SHARP_WIN, SHARP_HITS = 0.35, 10, 5   # on the unseen test camera), so this is a stage-camera rule
SHARP_REFRACTORY_S = 20.0


class LiveSharpRule:
    """A knife or scissors in someone's hands: the object overlaps (or touches) a person's box on 5 of the last 10
    frames. Fires weapon_visible (knife 0.85, scissors 0.6) at most every 20 s per object kind."""

    def __init__(self, on_event=None):
        self.on_event = on_event
        self.hits: dict[str, deque] = {k: deque(maxlen=SHARP_WIN) for k in SHARP.values()}
        self.last: dict[str, float] = {}
        self.boxes: dict[str, list] = {}

    def update(self, dets, now: float | None = None, frame=None) -> None:
        now = time.monotonic() if now is None else now
        people = [box for cls, _, _, box in dets if cls == PERSON]
        seen = {}
        for cls, _, conf, box in dets:
            kind = SHARP.get(cls)
            if kind and conf >= SHARP_CONF and any(_gap(box, p) < 0.15 for p in people):
                if kind not in seen or conf > seen[kind][0]:
                    seen[kind] = (conf, box)
        for kind, q in self.hits.items():
            q.append(kind in seen)
            if kind in seen:
                self.boxes[kind] = seen[kind][1]
            if sum(q) >= SHARP_HITS and kind in seen and now - self.last.get(kind, -1e9) >= SHARP_REFRACTORY_S:
                self.last[kind] = now
                if self.on_event:
                    self.on_event("weapon_visible", {"weapon": kind, "seen_frames": int(sum(q))}, seen[kind][1],
                                  0.85 if kind == "knife" else 0.6, float(seen[kind][0]), frame)

    def overlay(self, img, scale: float):
        import cv2
        for kind, q in self.hits.items():
            if sum(q) >= 2 and kind in self.boxes:
                x1, y1, x2, y2 = (int(v * scale) for v in self.boxes[kind])
                cv2.rectangle(img, (x1, y1), (x2, y2), (40, 40, 235), 3)
                cv2.putText(img, f"{kind} in hand", (x1, max(14, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            (40, 40, 235), 2, cv2.LINE_AA)
        return img


class LiveViolence:
    """Fights on the live camera, with the same models as uploads: pose rows kept for the last 2.5 s on a 30 fps
    clock, the pose (+ VideoMAE when available) random forest scored every second, an alert after two hot seconds
    in a row, then 15 s of quiet. VideoMAE runs on a background thread on the last ~2 s of whole frames."""

    WIN_S, STEP_S, P, REFRACTORY_S = 2.5, 1.0, 0.7, 15.0

    def __init__(self, on_event=None, use_videomae: bool = True):
        import joblib
        from argus.vision import violence as vio
        self.vio, self.on_event = vio, on_event
        self.models = joblib.load(vio.MODEL_PATH)
        self.rows: deque = deque()
        self.frames: deque = deque(maxlen=48)          # ~2 s of whole frames at 24 fps for VideoMAE
        self.vmae_p, self.p, self.prev_hot = None, 0.0, False
        self.last_eval, self.last_emit = 0.0, -1e9
        self.use_vmae = use_videomae
        self._vmae_busy = False
        if use_videomae:
            from argus.vision import violence_videomae as vm
            self.use_vmae = vm.available()

    def _vmae(self, frames):
        from argus.vision import violence_videomae as vm
        try:
            small = [cv2_resize(f) for f in frames]
            self.vmae_p = vm.prob(small)
        except Exception as exc:                       # the pose model alone still works
            print(f"[live] VideoMAE skipped: {exc}", flush=True)
            self.use_vmae = False
        finally:
            self._vmae_busy = False

    def update(self, pose_result, frame, now: float | None = None) -> None:
        import threading
        now = time.monotonic() if now is None else now
        f = int(now * 30)
        self.frames.append(frame)
        r = pose_result
        if r.boxes is not None and r.boxes.id is not None and r.keypoints is not None:
            for box, tid, cf, kp in zip(r.boxes.xyxy.tolist(), r.boxes.id.int().tolist(), r.boxes.conf.tolist(),
                                        r.keypoints.data.tolist()):
                self.rows.append({"frame": f, "tid": tid, "conf": cf, "xyxy": box, "kp": kp})
        while self.rows and self.rows[0]["frame"] < f - int(self.WIN_S * 30):
            self.rows.popleft()
        if self.use_vmae and not self._vmae_busy and now - self.last_eval >= self.STEP_S and len(self.frames) >= 16:
            self._vmae_busy = True
            threading.Thread(target=self._vmae, args=(list(self.frames),), daemon=True).start()
        if now - self.last_eval < self.STEP_S:
            return
        self.last_eval = now
        window = list(self.rows)
        if len({x["tid"] for x in window}) < 2:
            self.p, self.prev_hot = 0.0, False
            return
        x = self.vio.vector(self.vio.features(window, 30.0))
        if self.vmae_p is not None and "pose_videomae" in self.models:
            self.p = float(self.models["pose_videomae"]["model"].predict_proba([x + [self.vmae_p]])[0, 1])
        else:
            self.p = float(self.models.get("pose", self.models)["model"].predict_proba([x])[0, 1])
        hot = self.p >= self.P
        if hot and self.prev_hot and now - self.last_emit >= self.REFRACTORY_S and self.on_event:
            self.last_emit = now
            xs = [b for row in window for b in (row["xyxy"],)]
            box = [min(b[0] for b in xs), min(b[1] for b in xs), max(b[2] for b in xs), max(b[3] for b in xs)]
            self.on_event("violence", {"probability": round(self.p, 3), "model": "pose + VideoMAE" if self.vmae_p is not None
                                       else "pose", "people": len({x["tid"] for x in window})}, box,
                          min(0.95, 0.6 + 0.4 * self.p), self.p, frame)
        self.prev_hot = hot

    def overlay(self, img):
        import cv2
        col = (40, 40, 235) if self.p >= self.P else (80, 200, 120)
        cv2.putText(img, f"fight probability {self.p:.2f}", (12, img.shape[0] - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    col, 2, cv2.LINE_AA)
        return img


def cv2_resize(f, w: int = 480):
    import cv2
    h = int(f.shape[0] * w / f.shape[1])
    return cv2.resize(f, (w, h))


# ---- camera tamper: the view itself goes away ------------------------------------------------------------------
TAMPER_HOLD_S = 2.0              # the view must be gone this long (a hand passing the lens is not tampering)
TAMPER_CLEAR_S = 1.0             # and back this long before it counts as restored
TAMPER_LEARN = 15                # healthy frames that make the scene's baseline
FLAT_STD = 10.0                  # grey levels: a covered lens or a cap is nearly uniform
DARK_MEAN = 18.0                 # grey levels: blacked out
BLUR_FRAC = 0.12                 # detail (Laplacian variance) below this share of the scene's own baseline: sprayed or defocused


class LiveTamperRule:
    """The camera's own view is lost: covered, blacked out, or smeared. A monitoring system that cannot tell when its
    own eyes fail reports a covered camera as a quiet scene. Per frame, on a 160 px grey thumbnail: brightness, contrast
    (std) and detail (variance of the Laplacian) against the scene's own baseline, learned from its first healthy
    frames. Held TAMPER_HOLD_S -> camera_obstructed (severity 0.7, decisive: a person checks); back for TAMPER_CLEAR_S
    -> camera_restored (evidence on the same incident, with how long the view was gone)."""

    def __init__(self, on_event=None):
        self.on_event = on_event
        self.base_detail: float | None = None
        self._learn: list[float] = []
        self.bad_since: float | None = None
        self.good_since: float | None = None
        self.down_at: float | None = None
        self.reason = ""

    @staticmethod
    def measure(frame) -> tuple[float, float, float]:
        import cv2
        import numpy as np
        g = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = g.shape[:2]
        g = cv2.resize(g, (160, max(1, int(160 * h / max(w, 1)))), interpolation=cv2.INTER_AREA)
        return float(np.mean(g)), float(np.std(g)), float(cv2.Laplacian(g, cv2.CV_64F).var())

    def _why(self, mean: float, std: float, detail: float) -> str | None:
        if mean < DARK_MEAN:
            return "view blacked out"
        if std < FLAT_STD:
            return "lens covered (view is flat)"
        if self.base_detail and detail < BLUR_FRAC * self.base_detail:
            return "view smeared or out of focus"
        return None

    def update(self, frame, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        mean, std, detail = self.measure(frame)
        why = self._why(mean, std, detail)
        if why is None and self.base_detail is None:
            self._learn.append(detail)
            if len(self._learn) >= TAMPER_LEARN:
                self._learn.sort()
                self.base_detail = self._learn[len(self._learn) // 2]
        if why:
            self.good_since = None
            self.bad_since = self.bad_since if self.bad_since is not None else now
            self.reason = why
            if self.down_at is None and now - self.bad_since >= TAMPER_HOLD_S:
                self.down_at = self.bad_since
                if self.on_event:
                    self.on_event("camera_obstructed", {"reason": why, "brightness": round(mean, 1), "contrast": round(std, 1)},
                                  [0, 0, float(frame.shape[1]), float(frame.shape[0])], 0.7, 0.8, frame)
        else:
            self.bad_since = None
            self.good_since = self.good_since if self.good_since is not None else now
            if self.down_at is not None and now - self.good_since >= TAMPER_CLEAR_S:
                gone = round(self.good_since - self.down_at, 1)
                self.down_at = None
                if self.on_event:
                    self.on_event("camera_restored", {"view_lost_s": gone},
                                  [0, 0, float(frame.shape[1]), float(frame.shape[0])], 0.3, 0.9, frame)

    @property
    def obstructed(self) -> bool:
        return self.down_at is not None

    def overlay(self, img, now: float | None = None):
        import cv2
        now = time.monotonic() if now is None else now
        if self.bad_since is None:
            return img
        held = now - self.bad_since
        col = (40, 40, 235) if self.down_at is not None else (40, 170, 235)
        cv2.rectangle(img, (0, 0), (img.shape[1] - 1, img.shape[0] - 1), col, 6)
        cv2.putText(img, f"CAMERA VIEW LOST: {self.reason}  {held:4.1f} s", (16, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                    col, 2, cv2.LINE_AA)
        return img
