"""Violence from body motion: a small classifier on pose features, trained on real surveillance fight clips.

Features come from YOLO11s-pose tracks (run_pose.py) over a short window, in units that don't depend on camera
distance or frame rate (body heights and seconds):
  how close people are, how fast wrists and limbs move relative to the body's own motion, hands inside another
  person's box, how much bodies overlap, torso tilt and people lying down.

Training data: the Surveillance Camera Fight Dataset (Akti et al., IPTA 2019; MIT licence): 150 fight and 150
non-fight clips cut from real CCTV recordings. Evaluation is 5-fold cross-validation grouped by source recording,
so clips from the same camera recording never sit on both sides of a split.

Usage (repo root):  python backend/argus/vision/violence.py train
  -> models/violence.joblib and data/cache/violence_eval.json
"""
import json
import pathlib
import sys
from collections import defaultdict

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[3]
MODEL_PATH = ROOT / "models" / "violence.joblib"
FIGHTS = ROOT / "data" / "train" / "fights"
POSE_DIR = ROOT / "data" / "train" / "fights_pose"
KP_CONF = 0.3
WRISTS, SHOULDERS, HIPS = (9, 10), (5, 6), (11, 12)
FEATURES = ["n_people", "close_frac", "min_dist", "wrist_speed_p90", "wrist_speed_max", "limb_rel_p90",
            "limb_rel_max", "close_active_p90", "contact_frac", "iou_max", "center_speed_p90", "accel_p90",
            "tilt_p90", "lying_frac"]


def _group(rows: list[dict]) -> dict[int, list[dict]]:
    by = defaultdict(list)
    for r in rows:
        by[r["tid"]].append(r)
    return {k: sorted(v, key=lambda r: r["frame"]) for k, v in by.items()}


def _center(r):
    b = r["xyxy"]
    return np.array([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2])


def _height(r):
    return max(r["xyxy"][3] - r["xyxy"][1], 8.0)


def _kp(r) -> np.ndarray:
    return np.array(r["kp"], dtype=float)


def _mid(kp, idx):
    pts = [kp[i, :2] for i in idx if kp[i, 2] >= KP_CONF]
    return np.mean(pts, axis=0) if pts else None


def _iou(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    inter = w * h
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def features(rows: list[dict], fps: float) -> dict[str, float]:
    """Scene-level features for one window of pose rows (all people in view)."""
    tracks = _group(rows)
    frames = sorted({r["frame"] for r in rows})
    by_frame = defaultdict(list)
    for r in rows:
        by_frame[r["frame"]].append(r)
    wrist, limb_rel, center, accel, tilt, lying = [], [], [], [], [], []
    speed_by_tf: dict[tuple[int, int], float] = {}
    for tid, seq in tracks.items():
        prev_speed = None
        for a, b in zip(seq, seq[1:]):
            dt = (b["frame"] - a["frame"]) / fps
            if dt <= 0 or dt > 0.5:
                prev_speed = None
                continue
            h = (_height(a) + _height(b)) / 2
            ka, kb = _kp(a), _kp(b)
            ok = (ka[:, 2] >= KP_CONF) & (kb[:, 2] >= KP_CONF)
            c = (_center(b) - _center(a)) / h / dt
            cs = float(np.hypot(*c))
            center.append(cs)
            if ok.sum() >= 4:
                v = (kb[ok, :2] - ka[ok, :2]) / h / dt - c          # joint motion relative to the body's own motion
                rel = float(np.mean(np.hypot(v[:, 0], v[:, 1])))
                limb_rel.append(rel)
                speed_by_tf[(tid, b["frame"])] = rel
                if prev_speed is not None:
                    accel.append(abs(rel - prev_speed) / dt)
                prev_speed = rel
            ws = [float(np.hypot(*((kb[i, :2] - ka[i, :2]) / h / dt - c))) for i in WRISTS if ok[i]]
            if ws:
                wrist.append(max(ws))
        for r in seq:
            kp = _kp(r)
            s, hp = _mid(kp, SHOULDERS), _mid(kp, HIPS)
            if s is not None and hp is not None:
                d = s - hp
                tilt.append(float(np.degrees(np.arctan2(abs(d[0]), abs(d[1]) + 1e-6))))
            b = r["xyxy"]
            lying.append(float((b[2] - b[0]) > 1.1 * (b[3] - b[1])))
    dists, contact, ious, close_active = [], [], [], []
    for f in frames:
        people = by_frame[f]
        if len(people) < 2:
            continue
        best = 9.0
        touch = False
        for i in range(len(people)):
            for j in range(i + 1, len(people)):
                a, b = people[i], people[j]
                d = float(np.hypot(*(_center(a) - _center(b)))) / ((_height(a) + _height(b)) / 2)
                best = min(best, d)
                ious.append(_iou(a["xyxy"], b["xyxy"]))
                for p, q in ((a, b), (b, a)):
                    kp = _kp(p)
                    qb = q["xyxy"]
                    for w in WRISTS:
                        if kp[w, 2] >= KP_CONF and qb[0] <= kp[w, 0] <= qb[2] and qb[1] <= kp[w, 1] <= qb[3]:
                            touch = True
                if d < 1.0:
                    e = [speed_by_tf.get((p["tid"], f)) for p in (a, b)]
                    e = [x for x in e if x is not None]
                    if e:
                        close_active.append(max(e))
        dists.append(best)
        contact.append(float(touch))

    def pct(x, q):
        return float(np.percentile(x, q)) if x else 0.0

    counts = [len(by_frame[f]) for f in frames]
    return {
        "n_people": float(np.median(counts)) if counts else 0.0,
        "close_frac": float(np.mean([d < 1.0 for d in dists])) if dists else 0.0,
        "min_dist": float(min(dists)) if dists else 9.0,
        "wrist_speed_p90": pct(wrist, 90), "wrist_speed_max": max(wrist, default=0.0),
        "limb_rel_p90": pct(limb_rel, 90), "limb_rel_max": max(limb_rel, default=0.0),
        "close_active_p90": pct(close_active, 90),
        "contact_frac": float(np.mean(contact)) if contact else 0.0,
        "iou_max": max(ious, default=0.0),
        "center_speed_p90": pct(center, 90), "accel_p90": pct(accel, 90),
        "tilt_p90": pct(tilt, 90), "lying_frac": float(np.mean(lying)) if lying else 0.0,
    }


def vector(feat: dict[str, float]) -> list[float]:
    return [feat[k] for k in FEATURES]


def _groups() -> dict[str, str]:
    """clip name -> source recording (videos.txt lists each YouTube recording, then the clips cut from it)."""
    src, out = None, {}
    for line in (FIGHTS / "videos.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("http"):
            src = line
        elif ":" in line and src:
            out[line.split(":")[0].strip()] = src
    return out


def train() -> dict:
    import joblib
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
    from sklearn.model_selection import StratifiedGroupKFold

    groups = _groups()
    X, y, g, names = [], [], [], []
    for label, folder in ((1, "fight"), (0, "noFight")):
        for clip in sorted((FIGHTS / folder).glob("*")):
            p = POSE_DIR / f"{clip.stem}.pose.jsonl"
            if not p.exists():
                continue
            rows = [json.loads(x) for x in p.open(encoding="utf-8")]
            X.append(vector(features(rows, 25.0)))
            y.append(label)
            g.append(groups.get(clip.stem, clip.stem))
            names.append(clip.stem)
    X, y = np.array(X), np.array(y)
    clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.05, max_depth=4, random_state=0)
    prob = np.zeros(len(y))
    for tr, te in StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0).split(X, y, g):
        prob[te] = clf.fit(X[tr], y[tr]).predict_proba(X[te])[:, 1]
    pred = (prob >= 0.5).astype(int)
    res = {
        "dataset": "Surveillance Camera Fight Dataset (Akti et al. 2019, MIT)", "clips": int(len(y)),
        "fight": int(y.sum()), "no_fight": int(len(y) - y.sum()), "source_recordings": len(set(g)),
        "method": "5-fold cross-validation grouped by source recording; every clip scored by a model that never saw "
                  "its recording",
        "accuracy": round(accuracy_score(y, pred), 3), "precision": round(precision_score(y, pred), 3),
        "recall": round(recall_score(y, pred), 3), "f1": round(f1_score(y, pred), 3),
        "roc_auc": round(roc_auc_score(y, prob), 3),
        "fights_caught": int(((pred == 1) & (y == 1)).sum()), "false_alarms": int(((pred == 1) & (y == 0)).sum()),
    }
    clf.fit(X, y)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": clf, "features": FEATURES}, MODEL_PATH)
    out = ROOT / "data" / "cache" / "violence_eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))
    return res


if __name__ == "__main__":
    {"train": train}[sys.argv[1]]()
