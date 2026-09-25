"""Threat rules for high-security sites: a weapon on a person, violence between people, a person on the ground.

Inputs sit next to a clip's track file (same frame clock and pixel canvas as the other rules):
  <stem>.weapons.jsonl  run_weapons.py: YOLO11s fine-tuned on CCTV weapons (handgun / knife / rifle)
  <stem>.pose.jsonl     run_pose.py:    YOLO11s-pose tracks (17 body keypoints per person)
A clip without those files simply gets no threat events.

  weapon_visible  a weapon box on or next to a tracked person in WEAPON_MIN_HITS of WEAPON_WINDOW analysed frames
  violence        the violence classifier (violence.py) above VIOLENCE_P on two overlapping windows in a row
  person_down     a person lying down (box wider than tall, torso near horizontal) for at least DOWN_S seconds
  hand_off        two people's hands meet (wrists within HANDOFF_DIST body-heights) for HANDOFF_MIN_S, without a
                  fight: a hand-to-hand exchange. Scored against MEVA's person_transfers_object labels.
  dealing_pattern one person makes DEAL_MIN_HANDOFFS hand-offs with DEAL_MIN_PARTNERS different people within
                  DEAL_WINDOW_S while staying in about the same place: the shape of street dealing. Cameras
                  can't see what changes hands, so it is worded as a pattern for a human to judge.
Every threshold here was set before looking at any test result.
"""
from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path

import numpy as np

from argus.vision import violence as vio
from argus.vision.common import FPS

WEAPON_NAMES = {0: "handgun", 1: "knife", 2: "rifle"}
WEAPON_CONF = 0.5
WEAPON_WINDOW, WEAPON_MIN_HITS = 6, 3        # 3 of 6 analysed frames (~0.4 s at 15 fps)
WEAPON_REFRACTORY_S = 20.0
WEAPON_SEVERITY = {"handgun": 0.95, "rifle": 0.95, "knife": 0.85}
VIOLENCE_WIN_S, VIOLENCE_STEP_S, VIOLENCE_P = 2.5, 1.0, 0.7
VIOLENCE_REFRACTORY_S = 15.0
DOWN_S, DOWN_TILT = 3.0, 60.0
HANDOFF_DIST, HANDOFF_MIN_S, HANDOFF_GAP_S = 0.25, 0.4, 5.0
DEAL_MIN_HANDOFFS, DEAL_MIN_PARTNERS, DEAL_WINDOW_S, DEAL_STAY = 3, 2, 600.0, 1.5

_model = None


def _violence_model():
    global _model
    if _model is None and vio.MODEL_PATH.exists():
        import joblib
        _model = joblib.load(vio.MODEL_PATH)
    return _model


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(x) for x in f]


def apply(rules, track_path: Path) -> None:
    stem = rules.stem
    w = track_path.with_name(f"{stem}.weapons.jsonl")
    if w.exists():
        weapon_visible(rules, _read(w))
    p = track_path.with_name(f"{stem}.pose.jsonl")
    if p.exists():
        rows = _read(p)
        violence(rules, rows)
        person_down(rules, rows)
        dealing_pattern(rules, hand_off(rules, rows))


def _holder(rules, frame: int, box) -> tuple[int | None, list | None]:
    """The tracked person whose (slightly enlarged) box contains the weapon's centre."""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    best = (None, None, 1e9)
    for f in (frame, frame - 2, frame + 2):
        for tid, b in rules.by_frame.get(f, []):
            pw, ph = b[2] - b[0], b[3] - b[1]
            if b[0] - 0.3 * pw <= cx <= b[2] + 0.3 * pw and b[1] - 0.1 * ph <= cy <= b[3] + 0.1 * ph:
                d = abs(cx - (b[0] + b[2]) / 2) / max(pw, 1)
                if d < best[2]:
                    best = (tid, b, d)
    return best[0], best[1]


def weapon_visible(rules, rows: list[dict]) -> None:
    by_frame = defaultdict(list)
    for r in rows:
        if r["conf"] >= WEAPON_CONF:
            by_frame[r["frame"]].append(r)
    frames = sorted({r["frame"] for r in rows} | set(by_frame))
    recent: dict[str, deque] = defaultdict(lambda: deque(maxlen=WEAPON_WINDOW))
    last_emit: dict[tuple, float] = {}
    for f in frames:
        seen = defaultdict(list)
        for r in by_frame.get(f, []):
            seen[WEAPON_NAMES.get(r["cls"], "weapon")].append(r)
        for name in WEAPON_NAMES.values():
            recent[name].append(seen.get(name, []))
            hits = [x for x in recent[name] if x]
            if len(hits) < WEAPON_MIN_HITS or not seen.get(name):
                continue
            det = max(seen[name], key=lambda r: r["conf"])
            tid, pbox = _holder(rules, f, det["xyxy"])
            if tid is None:
                continue                      # a weapon-like shape with nobody holding it: posters, reflections
            key = (name, tid)
            if f - last_emit.get(key, -1e9) < WEAPON_REFRACTORY_S * FPS:
                continue
            last_emit[key] = f
            conf = float(np.mean([max(r["conf"] for r in x) for x in hits]))
            rules.emit("weapon_visible", f, WEAPON_SEVERITY[name], conf, tid, det["xyxy"],
                       weapon=name, held_by=f"{rules.cam}:t{tid}", seen_frames=len(hits), person_box=pbox)


def violence(rules, rows: list[dict]) -> None:
    model = _violence_model()
    if model is None or not rows:
        return
    frames = sorted({r["frame"] for r in rows})
    start, end = frames[0], frames[-1]
    win, step = int(VIOLENCE_WIN_S * FPS), int(VIOLENCE_STEP_S * FPS)
    prev_hot, last_emit = False, -1e9
    for a in range(start, max(start + 1, end - win + 1), step):
        window = [r for r in rows if a <= r["frame"] < a + win]
        if len({r["tid"] for r in window}) < 2:
            prev_hot = False
            continue
        feat = vio.features(window, FPS)
        p = float(model["model"].predict_proba([vio.vector(feat)])[0, 1])
        hot = p >= VIOLENCE_P
        if hot and prev_hot and a - last_emit >= VIOLENCE_REFRACTORY_S * FPS:
            last_emit = a
            box, tids = _hottest_pair(window)
            rules.emit("violence", a + win // 2, min(0.95, 0.6 + 0.4 * p), p, tids[0] if tids else 0, box,
                       probability=round(p, 3), people=[f"{rules.cam}:t{t}" for t in tids],
                       wrist_speed=round(feat["wrist_speed_p90"], 2), close=round(feat["close_frac"], 2))
        prev_hot = hot


def _hottest_pair(window: list[dict]):
    """Union box of the two closest people in the window's middle frame."""
    frames = sorted({r["frame"] for r in window})
    mid = [r for r in window if r["frame"] == frames[len(frames) // 2]] or window
    best = (None, 1e9)
    for i in range(len(mid)):
        for j in range(i + 1, len(mid)):
            a, b = mid[i]["xyxy"], mid[j]["xyxy"]
            d = np.hypot((a[0] + a[2] - b[0] - b[2]) / 2, (a[1] + a[3] - b[1] - b[3]) / 2)
            if d < best[1]:
                best = ((mid[i], mid[j]), d)
    if best[0] is None:
        r = mid[0]
        return r["xyxy"], [r["tid"]]
    a, b = best[0]
    box = [min(a["xyxy"][0], b["xyxy"][0]), min(a["xyxy"][1], b["xyxy"][1]),
           max(a["xyxy"][2], b["xyxy"][2]), max(a["xyxy"][3], b["xyxy"][3])]
    return box, [a["tid"], b["tid"]]


def person_down(rules, rows: list[dict]) -> None:
    by_tid = defaultdict(list)
    for r in rows:
        by_tid[r["tid"]].append(r)
    for tid, seq in by_tid.items():
        seq.sort(key=lambda r: r["frame"])
        since = None
        for r in seq:
            b, kp = r["xyxy"], np.array(r["kp"])
            s, h = vio._mid(kp, vio.SHOULDERS), vio._mid(kp, vio.HIPS)
            tilt = float(np.degrees(np.arctan2(abs((s - h)[0]), abs((s - h)[1]) + 1e-6))) if s is not None and h is not None else 0.0
            down = (b[2] - b[0]) > 1.1 * (b[3] - b[1]) and tilt >= DOWN_TILT
            if not down:
                since = None
                continue
            since = r["frame"] if since is None else since
            if r["frame"] - since >= DOWN_S * FPS:
                rules.emit("person_down", r["frame"], 0.75, min(0.95, r["conf"] + 0.1), tid, b,
                           down_s=round((r["frame"] - since) / FPS, 1), torso_tilt=round(tilt))
                break                          # one event per person


def hand_off(rules, rows: list[dict]) -> list[dict]:
    """Hands meeting between two people: any wrist of one within HANDOFF_DIST mean body-heights of any wrist of
    the other, on consecutive analysed frames for at least HANDOFF_MIN_S. Returns the hand-offs it emitted."""
    by_frame = defaultdict(list)
    for r in rows:
        by_frame[r["frame"]].append(r)
    streak: dict[tuple, list] = {}
    done: list[dict] = []
    last: dict[tuple, int] = {}
    for f in sorted(by_frame):
        people = by_frame[f]
        touching = set()
        for i in range(len(people)):
            for j in range(i + 1, len(people)):
                a, b = people[i], people[j]
                h = (vio._height(a) + vio._height(b)) / 2
                ka, kb = np.array(a["kp"]), np.array(b["kp"])
                wa = [ka[w, :2] for w in vio.WRISTS if ka[w, 2] >= vio.KP_CONF]
                wb = [kb[w, :2] for w in vio.WRISTS if kb[w, 2] >= vio.KP_CONF]
                if wa and wb and min(np.hypot(*(p - q)) for p in wa for q in wb) / h <= HANDOFF_DIST:
                    touching.add(tuple(sorted((a["tid"], b["tid"]))))
                    key = tuple(sorted((a["tid"], b["tid"])))
                    streak.setdefault(key, [f, a, b])[1:] = [a, b]
        for key in list(streak):
            if key in touching:
                continue
            start, a, b = streak.pop(key)
            if (f - start) / FPS >= HANDOFF_MIN_S and f - last.get(key, -1e9) >= HANDOFF_GAP_S * FPS:
                last[key] = f
                box = [min(a["xyxy"][0], b["xyxy"][0]), min(a["xyxy"][1], b["xyxy"][1]),
                       max(a["xyxy"][2], b["xyxy"][2]), max(a["xyxy"][3], b["xyxy"][3])]
                rules.emit("hand_off", start, 0.3, 0.6, key[0], box,
                           people=[f"{rules.cam}:t{t}" for t in key], duration_s=round((f - start) / FPS, 1))
                centre = {t: vio._center(p) for t, p in ((a["tid"], a), (b["tid"], b))}
                done.append({"frame": start, "tids": key, "centre": centre, "h": vio._height(a), "box": box})
    return done


def dealing_pattern(rules, handoffs: list[dict]) -> None:
    """One person, several hand-offs with different people, staying put (within DEAL_STAY body-heights)."""
    by_person = defaultdict(list)
    for ho in handoffs:
        for t in ho["tids"]:
            by_person[t].append(ho)
    for tid, hs in by_person.items():
        hs.sort(key=lambda h: h["frame"])
        for i in range(len(hs)):
            win = [h for h in hs[i:] if h["frame"] - hs[i]["frame"] <= DEAL_WINDOW_S * FPS]
            partners = {t for h in win for t in h["tids"] if t != tid}
            spots = np.array([h["centre"][tid] for h in win])
            spread = float(np.max(np.hypot(*(spots - spots.mean(axis=0)).T))) / max(win[0]["h"], 1) if len(win) > 1 else 0
            if len(win) >= DEAL_MIN_HANDOFFS and len(partners) >= DEAL_MIN_PARTNERS and spread <= DEAL_STAY:
                rules.emit("dealing_pattern", win[-1]["frame"], 0.6, 0.55, tid, win[-1]["box"],
                           handoffs=len(win), partners=len(partners),
                           minutes=round((win[-1]["frame"] - win[0]["frame"]) / FPS / 60, 1))
                break
