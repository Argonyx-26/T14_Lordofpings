"""False weapon alerts on ordinary CCTV: both weapon detectors over the 300 fight-dataset clips (no guns or knives;
bars, streets, shops; half of them fist fights), with the same alert rule as train_weapons.py alerts(): a weapon at
conf >= 0.5 on 3 of 6 consecutive analysed frames.

Usage (from backend/):  python -m argus.eval.weapons_fp       -> data/cache/weapons_fp.json
"""
import json
import sys
import time

from argus import settings
from argus.vision import train_weapons as tw

ROOT = settings.REPO_ROOT
CLIPS = sorted((ROOT / "data" / "train" / "fights").glob("*/*.mp4"))
STRIDE, CONF, WIN, HITS = 2, 0.5, 6, 3


def alerts(weights) -> dict:
    from ultralytics import YOLO
    m = YOLO(str(weights))
    flagged, frames_hit, frames = [], 0, 0
    for clip in CLIPS:
        hits = [len(r.boxes) > 0 for r in m.predict(str(clip), stream=True, imgsz=tw.IMGSZ, conf=CONF, vid_stride=STRIDE,
                                                    half=True, verbose=False)]
        frames, frames_hit = frames + len(hits), frames_hit + sum(hits)
        if any(sum(hits[i:i + WIN]) >= HITS for i in range(max(1, len(hits) - WIN + 1))):
            flagged.append(clip.stem)
    return {"clips": len(CLIPS), "clips_with_false_alert": len(flagged), "frames": frames,
            "frames_flagged": frames_hit, "flagged": flagged}


def main() -> int:
    out = {"dataset": "Surveillance Camera Fight Dataset (Akti et al. 2019): 300 CCTV clips, no weapons",
           "rule": f"conf >= {CONF} on {HITS} of {WIN} consecutive analysed frames (stride {STRIDE})"}
    for name, w in (("v1", tw.WEIGHTS), ("v2", tw.WEIGHTS_V2)):
        t0 = time.time()
        out[name] = alerts(w)
        print(f"{name}: {out[name]['clips_with_false_alert']}/{out[name]['clips']} clips with a false weapon alert, "
              f"{out[name]['frames_flagged']}/{out[name]['frames']} frames ({time.time() - t0:.0f} s)", flush=True)
    (settings.CACHE_DIR / "weapons_fp.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
