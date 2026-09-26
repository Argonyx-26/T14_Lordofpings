# Held-out results

The unchanged pipeline (vision rules, zones, thresholds and fusion exactly as tuned on 15 Mar 14:50-15:20) run on MEVA footage it never saw. Produced by `python -m argus.eval.holdout`.

| Window | Camera-hours | Staged incidents caught | False incidents | Raw events → incidents | Door sensor P / R (indoor) | Door P / R (all cameras) |
|---|---|---|---|---|---|---|
| Tuning window (15 Mar, 14:50-15:20) | 0.83 | 4 / 5 | 0 | 325 → 3 | 0.54 / 0.75 | 0.21 / 0.52 |
| **Held-out A**: Different day (5 Mar, 13:10-13:20) | 0.17 | 0 / 1 | 0 | 20 → 0 | n/a | n/a |

Notes:
- Held-out A streams: cctv, door.
  - Re-aimed since 15 Mar, so run with no zones (like an uploaded clip): G331, G336.
  - Staged theft at 2018-03-05 13:18:27 (G331): **missed**, incident score 24, sources cctv.
- A larger unseen sample (20 clips from seven days, nothing staged) is in `docs/SCALE_RESULTS.md`.
- Staged incidents are acted among real passers-by; MEVA dataset, Kitware Inc. / IARPA, CC-BY-4.0.
