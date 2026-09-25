"""Tracks + zone polygons -> CCTV events (severities follow the handoff §8 guide: <0.2 routine context)

 Tracks + zone polygons -> CCTV events (shared schema) -> data/events/cctv.jsonl

Usage: python backend/argus/vision/rules.py [track.jsonl ...]   (default: every file in data/tracks)

Rules only ever read YOLO tracks and camera polygons. Ground-truth theft/abandon
annotations are NEVER read here (they are for eval/evaluate.py only).
"""
from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field

import numpy as np
from shapely.geometry import Point, Polygon

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from argus.schema import Entity, Event, Media  # noqa: E402
from argus.vision import door_sensor  # noqa: E402
from argus.vision.common import EVENTS_DIR, FPS, TRACKS_DIR, camera_cfg, clip_info, frame_to_t  # noqa: E402

PERSON = 0
FRAME_W, FRAME_H = 1920, 1072
VEHICLES = {2, 3, 5, 7}
BAGS = {24, 26, 28, 63, 67}  # portable valuables: backpack, handbag, suitcase, laptop, cell phone
CLS_NAME = {0: "person", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck", 24: "backpack", 26: "handbag", 28: "suitcase",
            63: "laptop", 67: "cell phone"}

# Tunables (seconds are wall-clock seconds of footage)
ABANDON_S = 15.0          # owner away from a resting bag this long -> abandoned_object
BAG_STILL = 0.6           # bag counts as stationary if it drifts < this many bag-heights
CUSTODY_MIN_S = 1.0       # carrier != owner for at least this long
OWNER_WINDOW_S = 2.0      # owner = most frequent nearest person in the bag's first N s
NEAR = 0.6                # person "near" a bag if box distance < NEAR * person height
TAKEN_REST_S = 5.0        # an object resting this long that vanishes while a non-owner stands at it
TAKEN_GONE_S = 15.0       # ...and is not seen at that spot again for this long -> taken
RUN_SPEED = 1.8           # body-heights per second
RUN_MIN_S = 1.0
DOOR_GROUP_S = 4.0       # feet method: door-zone entries within this gap = one opening
DOOR_LOITER_S = 45.0
OCC_BUCKET_S = 10.0
OCC_Z = 2.5


@dataclass
class Track:
    tid: int
    cls: int
    frames: np.ndarray            # (N,)
    boxes: np.ndarray             # (N,4) xyxy
    conf: float
    chain: list[int] = field(default_factory=list)

    @property
    def centers(self):
        b = self.boxes
        return np.stack([(b[:, 0] + b[:, 2]) / 2, (b[:, 1] + b[:, 3]) / 2], 1)

    @property
    def feet(self):
        b = self.boxes
        return np.stack([(b[:, 0] + b[:, 2]) / 2, b[:, 3]], 1)

    @property
    def heights(self):
        return self.boxes[:, 3] - self.boxes[:, 1]


def load_tracks(path: pathlib.Path) -> dict[int, Track]:
    raw = defaultdict(list)
    with path.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            raw[d["tid"]].append((d["frame"], d["cls"], d["conf"], d["xyxy"]))
    tracks = {}
    for tid, rows in raw.items():
        rows.sort()
        cls = Counter(r[1] for r in rows).most_common(1)[0][0]
        # bag classes are often confused with each other; keep the family
        if cls in BAGS:
            rows = [r for r in rows if r[1] in BAGS]
        else:
            rows = [r for r in rows if r[1] == cls or (cls in VEHICLES and r[1] in VEHICLES)]
        tracks[tid] = Track(tid, cls, np.array([r[0] for r in rows]), np.array([r[3] for r in rows], float),
                            float(np.mean([r[2] for r in rows])), [tid])
    return tracks


def box_dist(pt, box) -> float:
    """Distance from a point to an xyxy rectangle (0 if inside)."""
    dx = max(box[0] - pt[0], 0, pt[0] - box[2])
    dy = max(box[1] - pt[1], 0, pt[1] - box[3])
    return float(np.hypot(dx, dy))


def iou(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / max((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter, 1e-6)


def link_bag_dets(path: pathlib.Path, ignore: list[Polygon]) -> tuple[dict[int, Track], dict]:
    """Low-confidence bag detections (run_bags.py) -> tracklets by greedy centre matching."""
    by_frame = defaultdict(list)
    with path.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            b = d["xyxy"]
            ctr = Point((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)
            if any(p.contains(ctr) for p in ignore):
                continue
            by_frame[d["frame"]].append(d)
    active: list[dict] = []
    done: list[dict] = []
    for fr in sorted(by_frame):
        dets = sorted(by_frame[fr], key=lambda d: -d["conf"])
        kept = []
        for d in dets:  # per-frame NMS across bag classes
            if all(iou(d["xyxy"], k["xyxy"]) < 0.5 for k in kept):
                kept.append(d)
        still = []
        for tr in active:
            (done if fr - tr["frames"][-1] > 1.5 * FPS else still).append(tr)
        active = still
        used = set()
        for d in kept:
            b = d["xyxy"]
            c = np.array([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2])
            best, bd = None, 1e9
            for k, tr in enumerate(active):
                if k in used:
                    continue
                lb = tr["boxes"][-1]
                dist = np.hypot(*(c - [(lb[0] + lb[2]) / 2, (lb[1] + lb[3]) / 2]))
                if dist < max(b[3] - b[1], lb[3] - lb[1]) and dist < bd:
                    best, bd = k, dist
            if best is None:
                active.append({"frames": [fr], "boxes": [b], "cls": [d["cls"]], "conf": [d["conf"]]})
                used.add(len(active) - 1)
            else:
                tr = active[best]
                tr["frames"].append(fr); tr["boxes"].append(b); tr["cls"].append(d["cls"]); tr["conf"].append(d["conf"])
                used.add(best)
    out = {}
    for n, tr in enumerate(done + active):
        if len(tr["frames"]) >= 5:
            tid = 100000 + n
            out[tid] = Track(tid, Counter(tr["cls"]).most_common(1)[0][0], np.array(tr["frames"]),
                             np.array(tr["boxes"], float), float(np.mean(tr["conf"])), [tid])
    return out, by_frame


def chain_bags(tracks: dict[int, Track]) -> list[Track]:
    """Bag tracks fragment when picked up/occluded. Join a track that starts within 3 s and
    ~2.5 bag-heights of where another ended."""
    bags = sorted((t for t in tracks.values() if t.cls in BAGS), key=lambda t: t.frames[0])
    out: list[Track] = []
    for t in bags:
        best = None
        for c in out:
            gap = t.frames[0] - c.frames[-1]
            if -1 * FPS <= gap <= 3 * FPS and t.frames[-1] > c.frames[-1]:  # small overlaps happen on NMS splits
                d = np.hypot(*(t.centers[0] - c.centers[-1]))
                if d < 2.5 * max(c.heights[-1], t.heights[0]) and (best is None or d < best[0]):
                    best = (d, c)
        if best:
            c = best[1]
            keep = t.frames > c.frames[-1]
            c.frames = np.concatenate([c.frames, t.frames[keep]])
            c.boxes = np.concatenate([c.boxes, t.boxes[keep]])
            c.chain.append(t.tid)
        else:
            out.append(Track(t.tid, t.cls, t.frames.copy(), t.boxes.copy(), t.conf, [t.tid]))
    return out


class ClipRules:
    def __init__(self, track_path: pathlib.Path):
        clip = clip_info(track_path.stem)
        self.stem, self.cam = clip.stem, clip.camera
        cfg = self.cfg = camera_cfg(self.cam)
        self.zone, self.area = cfg["zone"], cfg["area"]
        self.polys = {k: Polygon(v) for k, v in (cfg.get("polygons") or {}).items()}
        self.tracks = load_tracks(track_path)
        self.persons = {k: t for k, t in self.tracks.items() if t.cls == PERSON}
        bags_path = track_path.with_name(f"{self.stem}.bags.jsonl")
        ignore = [Polygon(p) for p in cfg.get("bag_ignore") or []]
        if bags_path.exists():  # prefer the dedicated low-conf bag pass
            self.bag_tracks, self.bag_dets = link_bag_dets(bags_path, ignore)
        else:
            self.bag_dets = None
            self.bag_tracks = {k: t for k, t in self.tracks.items() if t.cls in BAGS
                               and not any(p.contains(Point(*t.centers[0])) for p in ignore)}
        # frame -> [(tid, box)] for persons
        self.by_frame: dict[int, list] = defaultdict(list)
        for t in self.persons.values():
            for fr, b in zip(t.frames, t.boxes):
                self.by_frame[int(fr)].append((t.tid, b))
        self.events: list[dict] = []

    # ---------- helpers ----------
    def emit(self, type_, frame, severity, confidence, entity_id, bbox=None, kind="track", **attrs):
        self.events.append(dict(
            t=frame_to_t(self.stem, int(frame)), source="cctv", sensor_id=self.cam, zone=self.zone, area=self.area,
            type=type_,
            severity=round(severity, 3), confidence=round(confidence, 3),
            entity=Entity(kind=kind, id=f"{self.cam}:t{entity_id}" if kind == "track" else str(entity_id)),
            provenance="computed",
            media=Media(clip=self.stem, frame=int(frame), bbox=[round(float(v), 1) for v in (bbox if bbox is not None else [0, 0, 0, 0])]),
            attrs=attrs))

    def nearest_person(self, frame: int, pt, exclude=()):
        best = (None, 1e9, None)
        for tid, b in self.by_frame.get(frame, []):
            if tid in exclude:
                continue
            d = box_dist(pt, b) / max(b[3] - b[1], 1)
            if d < best[1]:
                best = (tid, d, b)
        return best

    def in_poly(self, name: str, pt) -> bool:
        return self.polys[name].contains(Point(float(pt[0]), float(pt[1])))

    def successors(self, tid: int) -> list[int]:
        """tid plus the tracks that continue it after a tracker ID switch (starts <1.5 s later, same spot)."""
        ids, t = [tid], self.persons[tid]
        while True:
            cand = [u for u in self.persons.values() if 0 < u.frames[0] - t.frames[-1] <= 1.5 * FPS
                    and np.hypot(*(u.feet[0] - t.feet[-1])) < 0.5 * t.heights[-1]]
            if not cand:
                return ids
            t = min(cand, key=lambda u: u.frames[0])
            ids.append(t.tid)

    def person_away(self, ids: list[int], frame: int, pt) -> bool:
        """Is this person (any of ids) more than 1.5 body-heights from pt, or gone from the scene?"""
        seen = False
        for x in ids:
            t = self.persons[x]
            k = int(np.argmin(np.abs(t.frames - frame)))
            if abs(t.frames[k] - frame) <= 10:
                seen = True
                if box_dist(pt, t.boxes[k]) / max(t.heights[k], 1) <= 3.0:
                    return False
        if seen:
            return True
        last = self.persons[ids[-1]]
        # Gone from view only counts if they left through a door; otherwise the tracker just lost them
        # (occlusion behind benches is common) and we can't claim the bag was abandoned.
        return frame > last.frames[-1] and self.leaves_scene(last)

    def leaves_scene(self, t: Track) -> bool:
        """Track ends at a door or walking out of the frame edge (not just lost mid-scene)."""
        x1, y1, x2, y2 = t.boxes[-1]
        at_edge = x1 < 40 or x2 > FRAME_W - 40 or y2 > FRAME_H - 20
        if at_edge:  # must be walking out, not sitting at the edge of the frame and then occluded
            # boxes get clipped at the edge, so measure the side of the box facing away from it
            k = int(np.searchsorted(t.frames, t.frames[-1] - 1.5 * FPS))
            b0, b1 = t.boxes[k], t.boxes[-1]
            if x2 > FRAME_W - 40:
                moved = b1[0] - b0[0]
            elif x1 < 40:
                moved = b0[2] - b1[2]
            else:
                moved = b1[1] - b0[1]
            at_edge = moved / max(t.heights[k], 1) > 0.25
        return bool(at_edge) or self.leaves_via_door(t)

    def walks_off(self, tid: int, frame: int, within_s: float = 10.0, min_heights: float = 1.5) -> bool:
        """Does this person (following ID switches) move away from where they are at `frame`?"""
        ids = self.successors(tid)
        t0 = self.persons[tid]
        k0 = int(np.argmin(np.abs(t0.frames - frame)))
        start, hgt = t0.feet[k0], max(t0.heights[k0], 1)
        for x in ids:
            t = self.persons[x]
            sel = (t.frames >= frame) & (t.frames <= frame + within_s * FPS)
            if sel.any() and (np.hypot(*(t.feet[sel] - start).T) / hgt).max() >= min_heights:
                return True
        last = self.persons[ids[-1]]
        return bool(last.frames[-1] <= frame + within_s * FPS and self.leaves_scene(last))

    def door_names(self):
        return [k for k in self.polys if k.startswith("door")]

    def leaves_via_door(self, t: Track) -> bool:
        """Track's last foot point is within half a body-height of a door polygon (tracker often
        loses people a step before the doorway)."""
        pt = Point(*t.feet[-1])
        if not any(self.polys[d].distance(pt) < 0.35 * t.heights[-1] for d in self.door_names()):
            return False
        # must be walking when the track ends (standing people lost behind furniture are not exits)
        k = int(np.searchsorted(t.frames, t.frames[-1] - 1.5 * FPS))
        b0, b1 = t.boxes[k], t.boxes[-1]
        moved = max(np.hypot(*(t.feet[-1] - t.feet[k])), abs(b1[0] - b0[0]), abs(b1[2] - b0[2]))
        return bool(moved / max(t.heights[k], 1) > 0.25)

    # ---------- rules ----------
    def door_activity(self):
        """One door_activity event per door OPENING (the metric the door sensor is scored on).

        door_method: leaf  -> video door-contact sensor: the upper door panel moves (door_sensor.py),
                              kept only when a person is at that door within +/-3 s
        door_method: feet  -> a person's feet enter the door zone; bursts within DOOR_GROUP_S at the
                              same door are one opening (a group walking through)
        """
        leaf_file = TRACKS_DIR / f"{self.stem}.doors.npz"
        if self.cfg.get("door_method", "feet") == "leaf" and leaf_file.exists():
            z = np.load(leaf_file)
            sig = {k: z[k] for k in z.files if k != "frames"}
            for door, frame, strength in door_sensor.door_events(z["frames"], sig):
                who = self.person_at_doors(frame, 3 * FPS)
                if who is None:
                    continue  # reflections / lighting, nobody at a door
                tid, box = who
                self.emit("door_activity", frame, 0.05, min(0.95, 0.5 + 0.1 * strength), tid, box,
                          door=door, method="door_leaf_motion", strength=strength)
        else:
            hits = []
            for t in self.persons.values():
                if len(t.frames) < 4:
                    continue
                for door in self.door_names():
                    inside = np.array([self.in_poly(door, p) for p in t.feet])
                    for i in range(len(inside)):
                        if inside[i] and (i == 0 or not inside[i - 1]):
                            direction = "in" if i == 0 else ("out" if inside[-1] else "pass")
                            hits.append((int(t.frames[i]), door, t, i, direction))
            last: dict = {}
            for frame, door, t, i, direction in sorted(hits, key=lambda h: h[0]):
                if frame - last.get(door, -1e9) > DOOR_GROUP_S * FPS:
                    self.emit("door_activity", frame, 0.05, min(0.95, t.conf + 0.2), t.tid, t.boxes[i],
                              door=door, direction=direction, method="feet_in_door_zone")
                last[door] = frame
        # loitering at a door (propping / tailgating wait)
        for t in self.persons.values():
            for door in self.door_names():
                inside = np.array([self.in_poly(door, p) for p in t.feet])
                span = t.frames[inside]
                if len(span) and span[-1] - span[0] > DOOR_LOITER_S * FPS and inside.mean() > 0.5:
                    j = int(np.argmax(inside))
                    self.emit("loitering", span[0] + DOOR_LOITER_S * FPS, 0.3, 0.6, t.tid, t.boxes[j],
                              polygon=door, dwell_s=round(float(span[-1] - span[0]) / FPS, 1))

    def person_at_doors(self, frame: int, window: float):
        """Nearest person to any door zone within +/-window frames: (tid, box) or None."""
        best = None
        for f in range(int(frame - window) // 2 * 2, int(frame + window) + 1, 2):
            for tid, b in self.by_frame.get(f, []):
                pt = Point((b[0] + b[2]) / 2, b[3])
                hgt = max(b[3] - b[1], 1)
                for d in self.door_names():
                    dist = self.polys[d].distance(pt) / hgt
                    if dist < 1.0 and (best is None or dist < best[0]):
                        best = (dist, tid, b)
        return None if best is None else (best[1], best[2])

    def bag_rules(self):
        for bag in chain_bags(self.bag_tracks):
            if len(bag.frames) < 8:
                continue
            emitted_custody = False
            c, h = bag.centers, np.maximum(bag.heights, 8)
            near = [self.nearest_person(int(f), p) for f, p in zip(bag.frames, c)]
            near_tid = [n[0] if n[1] < NEAR else None for n in near]

            # --- owner: most frequent nearby person while the bag is still at REST ---
            # A bag that is already moving when first seen is being carried by its owner, not stolen.
            moved = np.hypot(*(c - c[0]).T) > BAG_STILL * h
            k = int(np.argmax(moved)) if moved.any() else len(c)
            rest_s = (bag.frames[min(k, len(c) - 1)] - bag.frames[0]) / FPS
            rest_near = near_tid[:k]
            owners = Counter(x for x in rest_near if x is not None)
            owner = owners.most_common(1)[0][0] if owners and rest_s >= OWNER_WINDOW_S else None
            if owner is not None and owner in near_tid[k:k + 3]:
                owner = None  # the owner picked it up themselves -> handling, not custody change

            # --- custody_change: bag moving while its nearest person is B != owner ---
            if owner is not None:
                run_start, run_tid = None, None
                for i in range(1, len(bag.frames)):
                    j = max(0, i - 15)
                    moving = np.hypot(*(c[i] - c[j])) > 0.5 * h[i]
                    carrier = near_tid[i]
                    ok = moving and carrier is not None and carrier != owner
                    # both people must co-exist (a tracker ID switch creates a *new* tid at that instant)
                    if ok:
                        ct, ot = self.persons[carrier], self.persons[owner]
                        ok = ct.frames[0] < bag.frames[i] - FPS and ot.frames[-1] > bag.frames[i] - 2 * FPS
                    if ok:  # carrier was already next to the bag while it rested -> it's their own bag
                        ok = rest_near.count(carrier) <= 0.15 * max(len(rest_near), 1)
                    if ok:  # the bag must be leaving its owner (owner walking off with it = not a theft)
                        k_ = int(np.argmin(np.abs(ot.frames - bag.frames[i])))
                        if abs(ot.frames[k_] - bag.frames[i]) <= 10:
                            far = box_dist(c[i], ot.boxes[k_]) / max(ot.heights[k_], 1) > NEAR
                            k0 = int(np.argmin(np.abs(ot.frames - bag.frames[max(k - 1, 0)])))
                            owner_moved = np.hypot(*(ot.feet[k_] - ot.feet[k0])) / max(ot.heights[k0], 1)
                            bag_moved = np.hypot(*(c[i] - c[max(k - 1, 0)])) / h[max(k - 1, 0)]
                            ok = far or (bag_moved > 1.5 and owner_moved < 0.3)
                    if ok and run_tid == carrier:
                        if bag.frames[i] - run_start >= CUSTODY_MIN_S * FPS:
                            if not self.walks_off(carrier, int(run_start)):
                                break  # seated neighbours shuffling bags / detections hopping between them
                            exits = self.leaves_via_door(self.persons[carrier])
                            self.emit("custody_change", run_start, 0.6 if exits else 0.45, 0.8 if exits else 0.55, bag.tid, bag.boxes[i],
                                      object=CLS_NAME[bag.cls], owner=f"{self.cam}:t{owner}",
                                      carrier=f"{self.cam}:t{carrier}", carrier_exits_via_door=exits,
                                      bag_tracks=bag.chain)
                            emitted_custody = True
                            break
                    elif ok:
                        run_start, run_tid = bag.frames[i], carrier
                    else:
                        run_start, run_tid = None, None

            # --- custody_change (taken): a resting object vanishes while a non-owner stands at it ---
            # (thefts where the object disappears into a hand/pocket and is not tracked while carried)
            if self.bag_dets is not None and not emitted_custody:
                self.object_taken(bag, c, h, near_tid)

            # --- abandoned_object: bag at rest, and the person who set it down has walked away ---
            # (strangers sitting next to it don't count as attending it)
            i = 0
            while i < len(bag.frames):
                s_, j = i, i
                while j + 1 < len(bag.frames) and np.hypot(*(c[j + 1] - c[s_])) < BAG_STILL * h[s_]:
                    j += 1
                i = j + 1
                if bag.frames[j] - bag.frames[s_] < ABANDON_S * FPS:
                    continue
                # dropper = whoever is next to the bag the moment it appears (a seated stranger nearby
                # may be "nearest" more often later, so earliest wins)
                dropper = next((x for x in near_tid[s_:s_ + 4] if x is not None), None)
                if dropper is None:
                    continue  # nobody put it there -> background clutter
                ids = self.successors(dropper)
                away_since = None
                for q in range(s_, j + 1):
                    f = int(bag.frames[q])
                    if self.person_away(ids, f, c[q]):
                        away_since = f if away_since is None else away_since  # noqa: E501
                        if f - away_since >= ABANDON_S * FPS:
                            left = bool(f > max(self.persons[x].frames[-1] for x in ids))
                            self.emit("abandoned_object", f, 0.8 if left else 0.7, 0.65, bag.tid, bag.boxes[q],
                                      object=CLS_NAME[bag.cls], owner=f"{self.cam}:t{dropper}",
                                      dropped_frame=int(bag.frames[s_]), owner_away_frame=int(away_since),
                                      unattended_s=round((f - away_since) / FPS, 1), owner_left_scene=left)
                            break
                    else:
                        away_since = None

    def object_taken(self, bag: Track, c, h, near_tid):
        end = int(bag.frames[-1])
        last_frame = max(self.by_frame) if self.by_frame else end
        if end > last_frame - TAKEN_GONE_S * FPS:
            return  # clip ends too soon to know it's gone
        # resting span at the end of the track
        s_ = len(c) - 1
        while s_ > 0 and np.hypot(*(c[s_ - 1] - c[-1])) < BAG_STILL * h[-1]:
            s_ -= 1
        # it must really be gone: no detection of any valuable at that spot afterwards
        for f in range(end + 2, int(end + TAKEN_GONE_S * FPS), 2):
            for d in self.bag_dets.get(f, []):
                b = d["xyxy"]
                if np.hypot((b[0] + b[2]) / 2 - c[-1][0], (b[1] + b[3]) / 2 - c[-1][1]) < h[-1]:
                    return
        # taker: the person at the object when it vanished
        taker = None
        for f in range(end - 30, end + 31, 2):
            tid, d, _ = self.nearest_person(f, c[-1])
            if tid is not None and d < NEAR:
                taker = tid
                if f >= end:
                    break
        if taker is None:
            return
        # when did the object really arrive at this spot? (its track may have broken; walk back through raw dets)
        def here(fr):
            for d in self.bag_dets.get(fr, []):
                b = d["xyxy"]
                if np.hypot((b[0] + b[2]) / 2 - c[-1][0], (b[1] + b[3]) / 2 - c[-1][1]) < max(h[-1], 20):
                    return True
            return False
        first, f, miss = int(bag.frames[s_]), int(bag.frames[s_]), 0
        while f > 0 and miss < 6 * FPS:  # people standing in front hide it for a few seconds
            f -= 2
            if here(f):
                first, miss = f, 0
            else:
                miss += 2
        if end - first < TAKEN_REST_S * FPS:
            return
        # worn / held while its wearer stood still: centre inside someone's box most of the time
        inside = [box_dist(c[q], self.nearest_person(int(bag.frames[q]), c[q])[2]) == 0
                  for q in range(s_, len(c)) if self.nearest_person(int(bag.frames[q]), c[q])[2] is not None]
        if inside and np.mean(inside) > 0.6:
            return
        owner = None
        for f in range(first, first + int(FPS), 2):
            tid, d, _ = self.nearest_person(f, c[-1])
            if tid is not None and d < NEAR:
                owner = tid
                break
        if owner is not None and taker in self.successors(owner):
            return  # owner took it back
        # an owner standing nearby (distracted, back turned) can still be robbed; just less certain
        owner_near = owner is not None and not self.person_away(self.successors(owner), end, c[-1])
        chain = self.successors(taker)
        tt = self.persons[chain[-1]]
        k = int(np.searchsorted(tt.frames, end + 5 * FPS))
        k0 = int(np.searchsorted(self.persons[taker].frames, end))
        t0 = self.persons[taker]
        moved = np.hypot(*(tt.feet[min(k, len(tt.feet) - 1)] - t0.feet[min(k0, len(t0.feet) - 1)])) / max(t0.heights[0], 1)
        leaves = self.leaves_scene(tt)
        if moved < 1.0 and not leaves:
            return  # taker stays put -> probably just occluding it
        exits = self.leaves_via_door(tt)
        conf = (0.65 if exits else 0.45) - (0.1 if owner_near else 0.0)
        self.emit("custody_change", end, 0.6 if exits else 0.45, conf, bag.tid, bag.boxes[-1],
                  mode="taken", owner_nearby=owner_near, object=CLS_NAME[bag.cls], owner=f"{self.cam}:t{owner}" if owner is not None else None,
                  carrier=f"{self.cam}:t{taker}", carrier_exits_via_door=exits,
                  rested_s=round(float(end - first) / FPS, 1), bag_tracks=bag.chain)

    def vehicle_in_ped_zone(self):
        if "walkway" not in self.polys:
            return
        for t in self.tracks.values():
            if t.cls not in VEHICLES or len(t.frames) < 10:
                continue
            inside = [i for i, p in enumerate(t.feet) if self.in_poly("walkway", p)]
            if len(inside) >= 10:
                i = inside[0]
                self.emit("vehicle_in_ped_zone", t.frames[i], 0.45, 0.6, t.tid, t.boxes[i], vehicle=CLS_NAME[t.cls])

    def running(self):
        w = int(0.5 * FPS)
        for t in self.persons.values():
            if len(t.frames) < 10:
                continue
            f, p, h = t.frames, t.feet, np.maximum(t.heights, 20)
            fast_since = None
            for i in range(len(f)):
                j = int(np.searchsorted(f, f[i] - w))
                dt_ = (f[i] - f[j]) / FPS
                speed = np.hypot(*(p[i] - p[j])) / h[i] / dt_ if dt_ > 0.2 else 0
                if speed > RUN_SPEED:
                    fast_since = f[i] if fast_since is None else fast_since
                    if f[i] - fast_since >= RUN_MIN_S * FPS:
                        self.emit("running", fast_since, 0.35, 0.5, t.tid, t.boxes[i], speed_h_per_s=round(float(speed), 2))
                        break
                else:
                    fast_since = None

    def occupancy(self):
        if not self.by_frame:
            return
        last = max(self.by_frame)
        step = int(OCC_BUCKET_S * FPS)
        counts = []
        for s in range(0, last + 1, step):
            fr = [len(self.by_frame.get(f, [])) for f in range(s, s + step, 2)]
            counts.append(float(np.mean(fr)) if fr else 0.0)
        for k in range(6, len(counts)):
            hist = np.array(counts[k - 6:k])
            sd = max(hist.std(), 0.75)
            z = (counts[k] - hist.mean()) / sd
            if abs(z) > OCC_Z and abs(counts[k] - hist.mean()) >= 3:
                self.emit("occupancy", k * step, 0.05, 0.7, f"{self.cam}:occ", kind="area",
                          count=round(counts[k], 1), baseline=round(float(hist.mean()), 1), z=round(float(z), 2))
        # always emit a low-severity baseline every minute so the UI can chart occupancy
        per_min = int(60 / OCC_BUCKET_S)
        for k in range(0, len(counts), per_min):
            self.emit("occupancy", k * step, 0.05, 0.8, f"{self.cam}:occ", kind="area",
                      count=round(float(np.mean(counts[k:k + per_min])), 1), baseline=None, z=0.0)

    def run(self) -> list[dict]:
        self.door_activity()
        self.bag_rules()
        self.vehicle_in_ped_zone()
        self.running()
        self.occupancy()
        return self.events


def main(paths: list[pathlib.Path]):
    events = []
    for p in paths:
        ev = ClipRules(p).run()
        print(f"{p.stem}: {len(ev)} events  {dict(Counter(e['type'] for e in ev))}")
        events += ev
    events.sort(key=lambda e: e["t"])
    counters: Counter = Counter()
    out = EVENTS_DIR / "cctv.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for e in events:
            counters[e["sensor_id"]] += 1
            ev = Event(event_id=f"cctv-{e['sensor_id']}-{counters[e['sensor_id']]:06d}", **e)
            f.write(ev.model_dump_json() + "\n")
    print(f"wrote {len(events)} events -> {out}")


if __name__ == "__main__":
    args = [pathlib.Path(a) for a in sys.argv[1:]] or sorted(p for p in TRACKS_DIR.glob("*.jsonl") if p.name.count(".") == 5)  # <stem>.jsonl only
    main(args)
