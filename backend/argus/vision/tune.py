"""Quick vision-only check while tuning rules: which ground-truth incidents have a CCTV bag event
near them, and how many bag alerts fire elsewhere (false alarms). The full metrics live in eval/evaluate.py.

Usage: python backend/argus/vision/tune.py
"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from argus.config import site  # noqa: E402
from argus.ingest.groundtruth import load_ground_truth  # noqa: E402
from argus.settings import ANNOTATION_DIR, EVENTS_DIR, TRACKS_DIR  # noqa: E402

TOL = 30.0
BAG_TYPES = ("custody_change", "abandoned_object")

events = [json.loads(l) for l in (EVENTS_DIR / "cctv.jsonl").open()]
bag = [e for e in events if e["type"] in BAG_TYPES]
tracked = {p.name.removesuffix(".jsonl") for p in TRACKS_DIR.glob("*.jsonl") if not p.name.endswith(".bags.jsonl")}
used = set()
hits = n = 0
for g in load_ground_truth(ANNOTATION_DIR, site()):
    if g.clip not in tracked:
        print(f"  ----  {g.kind:17s} {g.camera} {g.clip[11:19]} (no tracks yet)")
        continue
    n += 1
    near = [e for e in bag if e["media"]["clip"] == g.clip and g.t_start - TOL <= e["t"] <= g.t_end + TOL]
    used |= {e["event_id"] for e in near}
    hits += bool(near)
    print(f"  {'HIT ' if near else 'MISS'}  {g.kind:17s} {g.camera} {g.clip[11:19]} frames {g.frames}"
          f" -> {[(e['type'], e['media']['frame'], e['severity']) for e in near]}")
print(f"recall {hits}/{n} on tracked clips")
fa = [e for e in bag if e["event_id"] not in used]
print(f"bag alerts away from ground truth: {len(fa)}")
for e in fa:
    print(f"   {e['event_id']} {e['type']} frame {e['media']['frame']} sev {e['severity']} {e['attrs'].get('object')}")
