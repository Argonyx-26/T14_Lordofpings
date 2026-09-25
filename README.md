# ARGUS — "We don't watch more, we notice sooner"

Team **Lord of the Pings** · ARGONYX '26 (RV University) · Problem Statement 5: *Intelligent Threat Detection and Situational Awareness System*.

ARGUS is a situational-awareness layer for security control rooms. It ingests several real-time streams (CCTV analytics, door sensors, device location), fuses weak signals that share an area and a time window into a handful of ranked, explained incidents, and keeps a human in charge of every decision.

## Data

The demo runs on **real footage and sensor data** from the [MEVA dataset](https://mevadata.org) (Kitware Inc. / IARPA, CC-BY-4.0): multi-camera 1080p video of a school, cafe, plaza and bus station at the Muscatatuck Urban Training Center, with real GPS tracks and human-annotated activities. Incidents in MEVA are staged by actors among ordinary passers-by.

| Stream | Source | Provenance |
|---|---|---|
| CCTV analytics | YOLO + ByteTrack run on the real footage | `computed` |
| Door sensor | MEVA door-open / entry / exit annotations | `annotation_derived` |
| Device location | MEVA GPS tracks (10 s fixes) | `recorded` |

Theft and abandoned-package annotations are **ground truth for evaluation only**; they are never fed into ARGUS.

Video, annotations and GPS are not stored in this repo. See `docs/HANDOFF_ARGUS_WINDOWS.md` and `scripts/`.

## How the vision works

No training and no labels: off-the-shelf COCO weights plus geometry. Everything runs on one laptop GPU (RTX 5060, 8 GB). Code is in `backend/argus/vision/`.

```
MEVA clip ─► run_tracks.py   YOLO11s + ByteTrack: people, vehicles, bags        ─► data/tracks/<clip>.jsonl
          ─► run_bags.py     YOLO11m @1280, conf 0.1: bags, laptops, phones      ─► <clip>.bags.jsonl
          ─► door_sensor.py  motion of the upper door leaf vs a 10 s median       ─► <clip>.doors.npz
                                   │
                  rules.py + zones.yaml (per-camera polygons drawn with draw_zones.py)
                                   ▼
          data/events/cctv.jsonl  (shared Event schema)  ─►  fusion engine
```

| Event | Rule (all thresholds in `rules.py`) |
|---|---|
| `custody_change` | A bag's owner is the person nearest it in its first 2 s. It fires when someone else carries it for ≥ 1 s, or when a resting bag vanishes while a non-owner stands at it and doesn't reappear for 15 s. |
| `abandoned_object` | A stationary bag whose owner has been more than 1.5 body-heights away, or out of the scene, for 15 s. |
| `door_activity` | Indoor doors: the video door-contact sensor (the top of the door panel moves above head height, with a person at the door within ±3 s). Outdoor or bus doors: a person's feet enter the door zone. |
| `running` | Speed of at least 1.8 body-heights per second, held for 1 s (body-heights make it independent of distance from the camera). |
| `occupancy` | 10 s head counts per camera, flagged when a count is more than 2.5 σ and 3 people away from the previous 60 s (causal, so there is no look-ahead). |

The low-confidence bag pass exists because small bags on the floor score 0.1–0.2, below the level ByteTrack will start a track on. So `rules.py` links those raw detections itself and re-joins bag tracks that fragment when a bag is picked up. Theft and abandonment annotations are never read by the vision code. `backend/argus/eval/evaluate.py` is the only thing that reads them.

**Measured** (MEVA 2018-03-15 14:50–15:20, 6 cameras, 9 clips; `python -m argus.eval.evaluate`):

| | Result |
|---|---|
| Staged incidents caught | **4 / 5** (2 thefts at the cafe, 1 theft and 1 abandonment at the bus station) |
| The miss | G331 theft at 14:56:54: a black purse on a black bench, which the detector never sees |
| Camera-level bag alerts not near any ground truth | 2. After fusion: **0 false incidents** (one was folded into the true bus-station incident, the other stayed below the incident threshold) |
| Funnel | 1,242 raw events → 20 per-stream alerts → **3 incidents** (99.8 % never reach an operator) |
| Door sensor, 3 indoor cameras (door-leaf method) | precision **0.54**, recall **0.75** (±2 s) |
| Door sensor, all 6 cameras | precision 0.21, recall 0.52. Exterior and bus-station doors use the feet heuristic, which fires on people queueing near a door (G331: 64 detections for 1 annotated opening). |
| Live tile (`live.py`, YOLO11s @960, FP16, 1080p cafe clip) | **30 fps** (the clip's real-time rate, which is the cap), 13–23 ms per frame for detection and tracking. With Windows Energy Saver on it drops to 23–27 fps (16–19 before `live.py` opted out of background power throttling). |

`static_change.py` (a dual-background "object removed or appeared" detector) does find the missed purse. But from video alone, that removal looks like someone leaving with their own bag, and a rule built on it added 12 false alarms. So it's experimental and switched off.

## Layout

```
backend/argus/   schema, ingest, replay clock, fusion + scoring, LLM brief, API, evaluation
backend/tests/   pytest suite (runs against the real 14:50–15:20 MEVA window when data/ is present)
frontend/        React + Vite + Tailwind console
scripts/         data download helpers
docs/            team handoff and plans
site/            project website, served at http://localhost:8000/site/ (see site/README.md)
```

## Run the demo (Windows laptop)

See **[docs/RUN_WINDOWS.md](docs/RUN_WINDOWS.md)**: `scripts\setup_windows.ps1` once, then `scripts\run_demo.ps1 -Prepare`. The whole demo is one process at http://localhost:8000.

## Run the backend for development (macOS / Linux / Windows)

```bash
python -m venv .venv && .venv/bin/pip install -r backend/requirements.txt   # Windows: .venv\Scripts\pip
scripts/get_meva_meta.sh                      # annotations + GPS (Windows: scripts/get_meva.ps1, includes video)
cd backend
../.venv/bin/python -m pytest -q              # 20 tests, real-data ones run when data/meva exists
../.venv/bin/python -m argus.eval.evaluate    # metrics vs ground truth -> data/cache/metrics.json
../.venv/bin/uvicorn argus.api.main:app --port 8000
```

The vision pipeline writes `data/events/cctv.jsonl` (one Event per line, schema in `backend/argus/schema.py`); the backend picks it up on restart. LLM briefs use Gemini when `GEMINI_API_KEY` is set in `.env` (or Claude when `ANTHROPIC_API_KEY` is), and fall back to a deterministic template otherwise (`ARGUS_LLM=off` forces the template).
