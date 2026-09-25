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
