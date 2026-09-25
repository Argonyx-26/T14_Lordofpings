# Held-out results

The unchanged pipeline (vision rules, zones, thresholds and fusion exactly as tuned on 15 Mar 14:50-15:20) run on MEVA footage it never saw. Produced by `python -m argus.eval.holdout`.

| Window | Camera-hours | Staged incidents caught | False incidents | Raw events → incidents | Door sensor P / R (indoor) | Door P / R (all cameras) |
|---|---|---|---|---|---|---|
| Tuning window (15 Mar, 14:50-15:20) | 0.75 | 0 / 5 | 0 | 1,070 → 1 | n/a | n/a |
| **Held-out A**: Different day (5 Mar, 13:10-13:20) | 0.17 | 0 / 1 | 0 | 20 → 0 | n/a | n/a |

Notes:
- Held-out A streams: cctv, door.
  - Staged theft at 2018-03-05 13:18:27 (G331): **missed**, incident score 24, sources cctv.
- Staged incidents are acted among real passers-by; MEVA dataset, Kitware Inc. / IARPA, CC-BY-4.0.
