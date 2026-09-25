# STATUS: demo laptop (Jack), auto-updated

_Updated Sat 26 Sep 02:05 IST. Refreshed every 5 min and pushed only when something changed. Details in HANDOFF.md._

## Now

- ✅ §2 laptop updated (setup 7/7, 25 tests, `-Prepare -Live`) · §8 Gemini plain-language briefs · §3 upload test (HANDOFF.md §9) · §4 real website screenshot (HANDOFF.md §10).
- ✅ The site's team section is Tanush + Mohit only (Utkarsh and Ojus didn't come). **Tanush: the pitch needs a two-speaker split, proposed in HANDOFF.md §10.**
- Next for Jack: §5 2-minute video (by 07:00), §6 Wi-Fi-off run-through, §7 slides 5–6.

## Demo laptop

- Backend + console: **up** at http://localhost:8000 · 1242 events · briefs by `gemini-flash-latest`
- Live tile: **down**
- AI briefs cached: 8
- Metrics: 4/5 caught · 1242 → 20 → 3

**Upload jobs (Analyse a video):**

- `cdd2679896` 2018-03-15.14-50-00.14-55-00.school.G421.avi (300.07 s): done, 9 events, 0 incidents
- `6b04d15f2a` 2018-03-15.15-15-00.15-20-00.bus.G331.avi (300.3 s): done, 9 events, 1 incident

## Recent commits on main

```
a553231 ARGUS investigator: a tool-using agent that works a case like an analyst (argus/agent.py). Gemini function calling over read-only tools: list_incidents, get_incident, search_signals, look_at_camera (real footage: three frames around a piece of evidence with the detector's box, or a whole frame, and a vision model answers one specific question), phones_in_area (who was there and where they went), forecast; finish writes the case file (verdict, confidence, answer, next step, cited ids). Tools only see the past up to the replay clock; the agent recommends, the operator acts; citations outside the log are dropped; 10-step and 3-look budgets with a forced finish; every step is kept for the console. Trust rule from our own measurement (the VLM missed 4 of 6 staged events): footage can confirm an alert, never dismiss one. Cached runs replay step by step offline; deterministic fallback without a key. POST /api/agent and GET /api/agent/stream (server-sent events, one per step). 4 tests
b47a81d Live incident on stage: the unattended-bag rule on the webcam (live.py --rules). A bag's owner is whoever brought it; it is abandoned when the owner leaves it for 15 s (bystanders don't count), with a countdown drawn on the stream. The alert and its still go to POST /api/live/event, join the replay in a 'Stage camera (live)' area and are fused, scored and briefed like any other signal; the console switches the camera wall to the live feed for that incident. Checked on the staged MEVA abandonment (G331 15:18): fires once, 0.3 s from the offline rule, owner-left; no alert for the platform's other bags. 4 tests. scale.py: numpy values in event attrs no longer crash the results file. train_weapons.py: v2 (+2,500 synthetic frames)
0e6d84a Links to the live website (argus-lordofpings.vercel.app: site, judges' page, offline console, Raah analytics) in the README, site/README.md and HANDOFF_TO_JACK Â§14
9dd1537 The ARGUS eye: a living instrument at the heart of the console (camera ring, three stream rings pulsing with live signal rates, signals flowing inward as particles with routine ones absorbed, pupil and iris dilating with the most urgent state, sweep at replay speed) in the situation band and the no-decision panel; boot sequence that opens the eye while the console links up (real readiness, hard 4.5 s cap, skippable, once per session) and flies it into the band; decoding incident titles, briefs that come into focus, spring re-ranking of the queue, rolling counts, glass HUD chips over footage; Motion's layout features lazy-loaded; theme colours emitted statically (the stream colours never reached the page). Website: real footage seen through the eye's aperture, opening with scroll to full bleed; inertial wheel scroll, sections that come into focus, decoding eyebrows, counting numbers (site/motion.js, no dependencies, offline, reduced-motion safe). Hosting without admin rights: scripts/build_site.sh + scripts/deploy_site.sh publish site + offline console with Raah analytics to Vercel; GitHub Pages workflow removed; README design section and new links
f50e47e Pages: Raah analytics (project proj_wwwp2pa8sqx7ytp4, domain argonyx-26.github.io) injected into the site, judges page and hosted console at build time; the offline demo on the laptop stays network-free
6f29088 README and judges page: fight detection at 76.7% / AUC 0.854 (pose + pretrained VideoMAE, 87/150 fights, 12 false) per 659e8df
d12960e What happens next, in the console and for uploads: 'Where this is heading' card and a response planner (crime-script stages with intervention points, what would change the score as bars on the site's bands, course-of-action comparison with a simulation, apply through the audit-logged action); Analyse a video becomes a threat assessment (verdict, risk over the clip, Airport / School / Park switch, forecast and planner per incident); offline demo snapshot carries forecasts (python -m argus.forecast snapshot); ?plan=1 and ?upload=<id> deep links. Packaging: CI (backend pytest, frontend lint/types/tests/build), GitHub Pages workflow (site + offline console, Raah when RAAH_PID is set; deploys once Pages is enabled), README rewritten (banner, badges, results with n and method, 90-second tour, mermaid architecture, forecasting method, privacy, AI disclosure, team), judges page, live-demo links on the site; HANDOFF_TO_JACK Â§14
659e8df Violence: pretrained surveillance video model fused with pose; accuracy 76.7 %, AUC 0.854 on 300 CCTV clips
```
