# STATUS: demo laptop (Jack), auto-updated

_Updated Fri 25 Sep 17:01 IST. Refreshed every 5 min and pushed only when something changed. Details in HANDOFF.md._

## Now

- ✅ §2 laptop updated (setup 7/7, 25 tests, `-Prepare -Live`), §8 Gemini plain-language briefs, §3 upload test (results in HANDOFF.md §9).
- ▶ Working on: §4 website screenshot of the bus-station incident, captured automatically (headless Chrome, `?incident=`).
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
c1f7f0d HANDOFF: GPU results of Analyse a video (bus 318 s, abandonment found, incident 72; cafe 298 s, 1 of 2 thefts, below watch); upload night-factor note
af10032 Demo video script as its own file: prep checklist, shot list with timings and voice-over, Clipchamp steps, honesty rules
784a0a1 Briefs in plain words (phones, bags changing hands; no internal type names), warm.py provider-aware key warning, setup_windows bootstraps pip in a uv venv; HANDOFF update
57485e5 HANDOFF_TO_JACK.md: what changed on Tanush's side and everything left to do on the demo laptop, in order
925a278 HANDOFF: mark npm-order and 20x run-sheet items resolved (a28ae32)
b4284fc Camera wall: smooth replay at 2-20x and boxes on the presented frame
63e65b5 Project website runs locally: bundled fonts, served by the backend at /site/, no analytics tag or deploy steps
dfc91f7 Project website: static showcase with real detection imagery, measured results, build log and team; Raah snippet, deploy guide and LinkedIn draft; console accepts ?incident= to preselect
```
