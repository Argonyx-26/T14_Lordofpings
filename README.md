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

## Layout

```
backend/argus/   schema, ingest, replay clock, fusion + scoring, LLM brief, API, evaluation
backend/tests/   pytest suite (runs against the real 14:50–15:20 MEVA window when data/ is present)
frontend/        React + Vite + Tailwind console
scripts/         data download helpers
docs/            team handoff and plans
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

The vision pipeline writes `data/events/cctv.jsonl` (one Event per line, schema in `backend/argus/schema.py`); the backend picks it up on restart. LLM briefs use the Claude API when `ANTHROPIC_API_KEY` is set in `.env` and fall back to a deterministic template otherwise (`ARGUS_LLM=off` forces the template).
