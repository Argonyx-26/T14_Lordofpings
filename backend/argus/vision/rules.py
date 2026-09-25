"""Tracks + zone polygons -> CCTV events (shared schema) -> data/events/cctv.jsonl

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
from argus.vision.common import EVENTS_DIR, FPS, TRACKS_DIR, camera_cfg, clip_info, frame_to_t  # noqa: E402

PERSON = 0
VEHICLES = {2, 3, 5, 7}
BAGS = {24, 26, 28}
CLS_NAME = {0: "person", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck", 24: "backpack", 26: "handbag", 28: "suitcase"}

# Tunables (seconds are wall-clock seconds of footage)
ABANDON_S = 20.0          # bag unattended this long -> abandoned_object
ABANDON_RADIUS = 3.0      # "attended" if a person box is within this many bag-heights
BAG_STILL = 0.6           # bag counts as stationary if it drifts < this many bag-heights
CUSTODY_MIN_S = 1.0       # carrier != owner for at least this long
OWNER_WINDOW_S = 2.0      # owner = most frequent nearest person in the bag's first N s
NEAR = 0.6                # person "near" a bag if box distance < NEAR * person height
RUN_SPEED = 1.8           # body-heights per second
RUN_MIN_S = 1.0
DOOR_COOLDOWN_S = 3.0
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
    with path.open() as f:
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


def link_bag_dets(path: pathlib.Path, ignore: list[Polygon]) -> dict[int, Track]:
    """Low-confidence bag detections (run_bags.py) -> tracklets by greedy centre matching."""
    by_frame = defaultdict(list)
    with path.open() as f:
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
    return out


def chain_bags(tracks: dict[int, Track]) -> list[Track]:
    """Bag tracks fragment when picked up/occluded. Join a track that starts within 3 s and
    ~2.5 bag-heights of where another ended."""
    bags = sorted((t for t in tracks.values() if t.cls in BAGS), key=lambda t: t.frames[0])
    out: list[Track] = []
    for t in bags:
        best = None
        for c in out:
            gap = t.frames[0] - c.frames[-1]
            if 0 < gap <= 3 * FPS:
                d = np.hypot(*(t.centers[0] - c.centers[-1]))
                if d < 2.5 * max(c.heights[-1], t.heights[0]) and (best is None or d < best[0]):
                    best = (d, c)
        if best:
            c = best[1]
            c.frames = np.concatenate([c.frames, t.frames])
            c.boxes = np.concatenate([c.boxes, t.boxes])
            c.chain.append(t.tid)
        else:
            out.append(Track(t.tid, t.cls, t.frames.copy(), t.boxes.copy(), t.conf, [t.tid]))
    return out


class ClipRules:
    def __init__(self, track_path: pathlib.Path):
        clip = clip_info(track_path.stem)
        self.stem, self.cam = clip.stem, clip.camera
        cfg = camera_cfg(self.cam)
        self.zone, self.area = cfg["zone"], cfg["area"]
        self.polys = {k: Polygon(v) for k, v in (cfg.get("polygons") or {}).items()}
        self.tracks = load_tracks(track_path)
        self.persons = {k: t for k, t in self.tracks.items() if t.cls == PERSON}
        bags_path = track_path.with_name(f"{self.stem}.bags.jsonl")
        ignore = [Polygon(p) for p in cfg.get("bag_ignore") or []]
        if bags_path.exists():  # prefer the dedicated low-conf bag pass
            self.bag_tracks = link_bag_dets(bags_path, ignore)
        else:
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

    def door_names(self):
        return [k for k in self.polys if k.startswith("door")]

    def leaves_via_door(self, t: Track) -> bool:
        """Track's last foot point is within half a body-height of a door polygon (tracker often
        loses people a step before the doorway)."""
        pt = Point(*t.feet[-1])
        return any(self.polys[d].distance(pt) < 0.5 * t.heights[-1] for d in self.door_names())

    # ---------- rules ----------
    def door_activity(self):
        for t in self.persons.values():
            if len(t.frames) < 4:
                continue
            for door in self.door_names():
                inside = np.array([self.in_poly(door, p) for p in t.feet])
                last_emit = -1e9
                for i in range(len(inside)):
                    entered = inside[i] and (i == 0 or not inside[i - 1])
                    if entered and t.frames[i] - last_emit > DOOR_COOLDOWN_S * FPS:
                        # direction: track born near the door = coming in; dies near the door = going out
                        direction = "in" if i == 0 else ("out" if inside[-1] else "pass")
                        self.emit("door_activity", t.frames[i], 0.1, min(0.95, t.conf + 0.2), t.tid, t.boxes[i],
                                  door=door, direction=direction)
                        last_emit = t.frames[i]
                # loitering at a door (propping / tailgating wait)
                span = t.frames[inside]
                if len(span) and span[-1] - span[0] > DOOR_LOITER_S * FPS and inside.mean() > 0.5:
                    j = int(np.argmax(inside))
                    self.emit("loitering", span[0] + DOOR_LOITER_S * FPS, 0.3, 0.6, t.tid, t.boxes[j],
                              polygon=door, dwell_s=round(float(span[-1] - span[0]) / FPS, 1))

    def bag_rules(self):
        for bag in chain_bags(self.bag_tracks):
            if len(bag.frames) < 8:
                continue
            c, h = bag.centers, np.maximum(bag.heights, 8)
            near = [self.nearest_person(int(f), p) for f, p in zip(bag.frames, c)]
            near_tid = [n[0] if n[1] < NEAR else None for n in near]

            # --- owner: most frequent nearby person while the bag is still at REST ---
            # A bag that is already moving when first seen is being carried by its owner, not stolen.
            moved = np.hypot(*(c - c[0]).T) > BAG_STILL * h
            k = int(np.argmax(moved)) if moved.any() else len(c)
            rest_s = (bag.frames[min(k, len(c) - 1)] - bag.frames[0]) / FPS
            owners = Counter(x for x in near_tid[:k] if x is not None)
            owner = owners.most_common(1)[0][0] if owners and rest_s >= OWNER_WINDOW_S else None

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
                    if ok:  # the bag must be leaving its owner (owner still holding / pushing it = not a theft)
                        k_ = int(np.argmin(np.abs(ot.frames - bag.frames[i])))
                        if abs(ot.frames[k_] - bag.frames[i]) <= 10:
                            ok = box_dist(c[i], ot.boxes[k_]) / max(ot.heights[k_], 1) > NEAR
                    if ok and run_tid == carrier:
                        if bag.frames[i] - run_start >= CUSTODY_MIN_S * FPS:
                            exits = self.leaves_via_door(self.persons[carrier])
                            self.emit("custody_change", run_start, 0.85 if exits else 0.7, 0.55, bag.tid, bag.boxes[i],
                                      object=CLS_NAME[bag.cls], owner=f"{self.cam}:t{owner}",
                                      carrier=f"{self.cam}:t{carrier}", carrier_exits_via_door=exits,
                                      bag_tracks=bag.chain)
                            break
                    elif ok:
                        run_start, run_tid = bag.frames[i], carrier
                    else:
                        run_start, run_tid = None, None

            # --- abandoned_object: stationary + nobody within ABANDON_RADIUS bag-heights ---
            start = None
            for i in range(len(bag.frames)):
                f = int(bag.frames[i])
                d = min((box_dist(c[i], b) for _, b in self.by_frame.get(f, [])), default=1e9)
                alone = d > ABANDON_RADIUS * h[i]
                still = start is not None and np.hypot(*(c[i] - c[start])) < BAG_STILL * h[i]
                if alone and (still or start is None):
                    start = i if start is None else start
                    if bag.frames[i] - bag.frames[start] >= ABANDON_S * FPS:
                        last_owner = next((x for x in reversed(near_tid[:start + 1]) if x is not None), owner)
                        if last_owner is None:  # never near anyone -> background clutter, not a dropped bag
                            break
                        owner_left = None
                        if last_owner is not None:
                            ot = self.persons[last_owner]
                            owner_left = bool(ot.frames[-1] < bag.frames[i])
                        self.emit("abandoned_object", bag.frames[start], 0.9 if owner_left else 0.75, 0.6, bag.tid,
                                  bag.boxes[i], object=CLS_NAME[bag.cls],
                                  unattended_s=round(float(bag.frames[i] - bag.frames[start]) / FPS, 1),
                                  owner=f"{self.cam}:t{last_owner}" if last_owner is not None else None,
                                  owner_left_scene=owner_left)
                        break
                else:
                    start = i if alone else None

    def vehicle_in_ped_zone(self):
        if "walkway" not in self.polys:
            return
        for t in self.tracks.values():
            if t.cls not in VEHICLES or len(t.frames) < 10:
                continue
            inside = [i for i, p in enumerate(t.feet) if self.in_poly("walkway", p)]
            if len(inside) >= 10:
                i = inside[0]
                self.emit("vehicle_in_ped_zone", t.frames[i], 0.6, 0.6, t.tid, t.boxes[i], vehicle=CLS_NAME[t.cls])

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
                        self.emit("running", fast_since, 0.4, 0.5, t.tid, t.boxes[i], speed_h_per_s=round(float(speed), 2))
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
                self.emit("occupancy", k * step, 0.25 if z > 0 else 0.1, 0.7, f"{self.cam}:occ", kind="area",
                          count=round(counts[k], 1), baseline=round(float(hist.mean()), 1), z=round(float(z), 2))
        # always emit a low-severity baseline every minute so the UI can chart occupancy
        per_min = int(60 / OCC_BUCKET_S)
        for k in range(0, len(counts), per_min):
            self.emit("occupancy", k * step, 0.0, 0.8, f"{self.cam}:occ", kind="area",
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
    with out.open("w") as f:
        for e in events:
            counters[e["sensor_id"]] += 1
            ev = Event(event_id=f"cctv-{e['sensor_id']}-{counters[e['sensor_id']]:06d}", **e)
            f.write(ev.model_dump_json() + "\n")
    print(f"wrote {len(events)} events -> {out}")


if __name__ == "__main__":
    args = [pathlib.Path(a) for a in sys.argv[1:]] or sorted(p for p in TRACKS_DIR.glob("*.jsonl") if not p.name.endswith(".bags.jsonl"))
    main(args)
