# STATUS: demo laptop (Jack), auto-updated

_Updated Fri 25 Sep 22:17 IST. Refreshed every 5 min and pushed only when something changed. Details in HANDOFF.md._

## Now

- ✅ §2 laptop updated (setup 7/7, 25 tests, `-Prepare -Live`) · §8 Gemini plain-language briefs · §3 upload test (HANDOFF.md §9) · §4 real website screenshot (HANDOFF.md §10).
- ✅ The site's team section is Tanush + Mohit only (Utkarsh and Ojus didn't come). **Tanush: the pitch needs a two-speaker split, proposed in HANDOFF.md §10.**
- Next for Jack: §5 2-minute video (by 07:00), §6 Wi-Fi-off run-through, §7 slides 5–6.

## Demo laptop

- Backend + console: **up** at http://localhost:8000 · 1242 events · briefs by `gemini-flash-latest`
- Live tile: **down**
- AI briefs cached: 7
- Metrics: 4/5 caught · 1242 → 20 → 3

**Upload jobs (Analyse a video):**

- `cdd2679896` 2018-03-15.14-50-00.14-55-00.school.G421.avi (300.07 s): done, 9 events, 0 incidents
- `6b04d15f2a` 2018-03-15.15-15-00.15-20-00.bus.G331.avi (300.3 s): done, 9 events, 1 incident

## Recent commits on main

```
84af8e5 Violence classifier: random forest on pose features, 300 surveillance fight/no-fight clips, 5-fold CV grouped by source recording: accuracy 0.747, AUC 0.821 (dataset authors' best: 72% on a random 80/20 split); at the pipeline threshold 0.7: 80/150 fights, 17/150 false alarms (precision 0.825)
c9f75b9 scale.py: camera-view check by phase-correlation shift of edge maps (re-aimed G331/G336 shift 26-77 px, same-view clips 0-3 px; the edge-correlation check wrongly rejected same-view clips in evening light)
3944daf eval/scale.py: large-sample door-sensor and hand-off evaluation on 306 unseen MEVA clips (1,337 door openings, 176 transfers, seven days), with a camera-view check, resumable, laptop sample or full run on a GPU server
41724e6 Uploads run the pose and weapon passes (when their models exist) on the rules' canvas, so fights, falls, hand-offs and weapons show up in 'Analyse a video'; pose/weapon rows use even frames on the 30 fps clock
2b212dd Security profiles (airport / school-college / public park) and threat detectors (weapons, violence, person down, hand-offs, dealing pattern)
26774e6 Site: console screenshot retaken with the redesigned console (15:18:40, INC-0007, real G331 footage with detections, Gemini brief, evidence still), new alt text and caption (HANDOFF_TO_JACK Â§13)
5ff06e8 HANDOFF_TO_JACK Â§13: retake the site screenshot with the new console (seek to 15:18:40, INC-0007, 1536x864; new alt text and caption)
acf0e5f Console redesign: situation band (what is happening, signals-to-decisions funnel, ground-truth accuracy with per-incident detail), replay bar with click-to-seek timeline and incident markers, one main camera that follows the selected incident plus a filmstrip (tiles swap without reloading video; live detection counts, box key, evidence labels in plain words), incident panel with response progress (signals -> opened by ARGUS -> human decision), risk gauge, collapsible score breakdown and hash-chained decision log, Respond menu (recommended action, acknowledge, dispatch guard, escalate, notify police, dismiss as false alarm; extra actions recorded as audit notes), Ask ARGUS moved to a header popover (/), raw signals collapsed to a ticker, status symbols with shape + colour, source icons, responsive down to phone width; overlay redraws only on new frames, mock data lazy-loaded (main bundle 337 -> 318 kB); demo script and pitch updated for the new controls
```
