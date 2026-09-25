# STATUS: demo laptop (Jack), auto-updated

_Updated Fri 25 Sep 20:07 IST. Refreshed every 5 min and pushed only when something changed. Details in HANDOFF.md._

## Now

- ✅ §2 laptop updated (setup 7/7, 25 tests, `-Prepare -Live`) · §8 Gemini plain-language briefs · §3 upload test (HANDOFF.md §9) · §4 real website screenshot (HANDOFF.md §10).
- ✅ The site's team section is Tanush + Mohit only (Utkarsh and Ojus didn't come). **Tanush: the pitch needs a two-speaker split, proposed in HANDOFF.md §10.**
- Next for Jack: §5 2-minute video (by 07:00), §6 Wi-Fi-off run-through, §7 slides 5–6.

## Demo laptop

- Backend + console: **up** at http://localhost:8000 · 1242 events · briefs by `gemini-flash-latest`
- Live tile: **up** · 30 fps (rounded)
- AI briefs cached: 7
- Metrics: 4/5 caught · 1242 → 20 → 3

**Upload jobs (Analyse a video):**

- `cdd2679896` 2018-03-15.14-50-00.14-55-00.school.G421.avi (300.07 s): done, 9 events, 0 incidents
- `6b04d15f2a` 2018-03-15.15-15-00.15-20-00.bus.G331.avi (300.3 s): done, 9 events, 1 incident

## Recent commits on main

```
958d9de Evidence stills for uploaded videos: the worker renders them from the original clip (rules canvas mapped back to the clip's frames and pixels; never fails a job), GET /api/uploads/{job}/thumbs/{event}.jpg, a key frame on each upload incident and a still on each event; Still is a shared component
7ed1a3b HANDOFF Â§11 update: set A result and why it missed, set C, merged report, timing, Ask offline warm-up
4f77271 Ask ARGUS: python -m argus.ask "<local time>" "<question>" pre-answers a rehearsed question at that replay moment, so it is served from the cache on stage without Wi-Fi
19cebd3 Held-out set C (12 Mar 10:00-10:15, all six cameras with the tuned views + GPS, nothing staged); --set takes several sets and the report merges earlier runs instead of overwriting them; vision/bench.py for GPU throughput (cameras per GPU)
d30850d HANDOFF Â§11: held-out fixes (re-aimed cameras, missing theft annotation), evidence stills, Ask ARGUS, failed AI second-opinion experiment (vlm_check.py), Bengaluru hook checked
aabfae6 Ask ARGUS: plain-language questions answered only from the log so far, with clickable citations
0124cff Evidence stills in the incident panel; held-out set A treats re-aimed cameras as new
c510a7b Held-out evaluation (python -m argus.eval.holdout): unchanged pipeline on unseen MEVA footage (5 Mar with one staged theft; 15 Mar 15:30-15:40, all cameras + GPS), writes docs/HOLDOUT_RESULTS.md; door-sensor experiment and overfitting / sample-size / door answers in the pitch; handoff Â§12 for Jack
```
