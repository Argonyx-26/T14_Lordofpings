# STATUS: demo laptop (Jack), auto-updated

_Updated Fri 25 Sep 18:44 IST. Refreshed every 5 min and pushed only when something changed. Details in HANDOFF.md._

## Now

- ✅ §2 laptop updated (setup 7/7, 25 tests, `-Prepare -Live`) · §8 Gemini plain-language briefs · §3 upload test (HANDOFF.md §9) · §4 real website screenshot (HANDOFF.md §10).
- ✅ The site's team section is Tanush + Mohit only (Utkarsh and Ojus didn't come). **Tanush: the pitch needs a two-speaker split, proposed in HANDOFF.md §10.**
- Next for Jack: §5 2-minute video (by 07:00), §6 Wi-Fi-off run-through, §7 slides 5–6.

## Demo laptop

- Backend + console: **up** at http://localhost:8000 · 1242 events · briefs by `gemini-flash-latest`
- Live tile: **up** · 10 fps (rounded)
- AI briefs cached: 7
- Metrics: 4/5 caught · 1242 → 20 → 3

**Upload jobs (Analyse a video):**

- `cdd2679896` 2018-03-15.14-50-00.14-55-00.school.G421.avi (300.07 s): done, 9 events, 0 incidents
- `6b04d15f2a` 2018-03-15.15-15-00.15-20-00.bus.G331.avi (300.3 s): done, 9 events, 1 incident

## Recent commits on main

```
c510a7b Held-out evaluation (python -m argus.eval.holdout): unchanged pipeline on unseen MEVA footage (5 Mar with one staged theft; 15 Mar 15:30-15:40, all cameras + GPS), writes docs/HOLDOUT_RESULTS.md; door-sensor experiment and overfitting / sample-size / door answers in the pitch; handoff Â§12 for Jack
1a7685b Story titles (unattended object then carried off = possible theft), decisive signals open on their own, quick-scan uploads, false-incident metric and indoor door split in a shared evaluator, vision-rule regression tests, headline-number guard, frontend unit tests (vitest)
e209fdf Review fixes: resilient replay loop, safe broadcasts, read endpoints on the event loop, bounded buffers, thread-safe upload manager, ffmpeg failure handling, upload duration fallback, memoised upload overlay; dead code removed; repo-relative transcode.ps1; stale docs updated
79ffd6d Site: team is Tanush and Mohit (Utkarsh and Ojus did not attend), 2-column team grid; HANDOFF: two-speaker split for the pitch
4d234ed Site: real console screenshot (bus-station incident at 15:18:40, Gemini brief), caption no longer says sample data; HANDOFF Â§10
35f922c Uploads stamped at noon so unknown time of day never gets the night factor (per Jack's GPU test); test; note in HANDOFF_TO_JACK
c1f7f0d HANDOFF: GPU results of Analyse a video (bus 318 s, abandonment found, incident 72; cafe 298 s, 1 of 2 thefts, below watch); upload night-factor note
af10032 Demo video script as its own file: prep checklist, shot list with timings and voice-over, Clipchamp steps, honesty rules
```
