# STATUS: demo laptop (Jack), auto-updated

_Updated Fri 25 Sep 23:29 IST. Refreshed every 5 min and pushed only when something changed. Details in HANDOFF.md._

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
f50e47e Pages: Raah analytics (project proj_wwwp2pa8sqx7ytp4, domain argonyx-26.github.io) injected into the site, judges page and hosted console at build time; the offline demo on the laptop stays network-free
6f29088 README and judges page: fight detection at 76.7% / AUC 0.854 (pose + pretrained VideoMAE, 87/150 fights, 12 false) per 659e8df
d12960e What happens next, in the console and for uploads: 'Where this is heading' card and a response planner (crime-script stages with intervention points, what would change the score as bars on the site's bands, course-of-action comparison with a simulation, apply through the audit-logged action); Analyse a video becomes a threat assessment (verdict, risk over the clip, Airport / School / Park switch, forecast and planner per incident); offline demo snapshot carries forecasts (python -m argus.forecast snapshot); ?plan=1 and ?upload=<id> deep links. Packaging: CI (backend pytest, frontend lint/types/tests/build), GitHub Pages workflow (site + offline console, Raah when RAAH_PID is set; deploys once Pages is enabled), README rewritten (banner, badges, results with n and method, 90-second tour, mermaid architecture, forecasting method, privacy, AI disclosure, team), judges page, live-demo links on the site; HANDOFF_TO_JACK Â§14
659e8df Violence: pretrained surveillance video model fused with pose; accuracy 76.7 %, AUC 0.854 on 300 CCTV clips
cb040c4 Forecast and response planning (argus/forecast.py): crime-script stage (precursor -> commission -> departure, playbook scripts), what would change the score (next stages, another sensor agreeing, night, other profiles, dismissal) re-scored with the real scorer at each signal's usual strength, course-of-action comparison (time to effect from guard posts and stated service times, stage disrupted, people affected from GPS, disruption, decision recorded) ranked by a stated rule; GET /api/incidents/{id}/forecast; uploads get a threat assessment (verdict, risk timeline, forecasts) re-fused under any profile via GET /api/uploads/{id}/assess; 8 tests
2f37032 HANDOFF Â§12: mentor round (profiles, weapons, violence, person down, hand-offs, dealing pattern) with numbers, n and method, and what to say on stage
2355441 Weapon detector results on an unseen camera (Cam7, 3,511 frames): AP50 handgun 0.51, rifle 0.54, knife 0.09; alert level 42/84 weapon appearances, 14 false alerts in 29 min (dark phones in hand); train_weapons.py alerts reproduces it; scale.py also runs the weapon pass and logs threat events on ordinary footage
84af8e5 Violence classifier: random forest on pose features, 300 surveillance fight/no-fight clips, 5-fold CV grouped by source recording: accuracy 0.747, AUC 0.821 (dataset authors' best: 72% on a random 80/20 split); at the pipeline threshold 0.7: 80/150 fights, 17/150 false alarms (precision 0.825)
```
