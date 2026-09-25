# STATUS: demo laptop (Jack), auto-updated

_Updated Fri 25 Sep 21:56 IST. Refreshed every 5 min and pushed only when something changed. Details in HANDOFF.md._

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
41724e6 Uploads run the pose and weapon passes (when their models exist) on the rules' canvas, so fights, falls, hand-offs and weapons show up in 'Analyse a video'; pose/weapon rows use even frames on the 30 fps clock
2b212dd Security profiles (airport / school-college / public park) and threat detectors (weapons, violence, person down, hand-offs, dealing pattern)
26774e6 Site: console screenshot retaken with the redesigned console (15:18:40, INC-0007, real G331 footage with detections, Gemini brief, evidence still), new alt text and caption (HANDOFF_TO_JACK Â§13)
5ff06e8 HANDOFF_TO_JACK Â§13: retake the site screenshot with the new console (seek to 15:18:40, INC-0007, 1536x864; new alt text and caption)
acf0e5f Console redesign: situation band (what is happening, signals-to-decisions funnel, ground-truth accuracy with per-incident detail), replay bar with click-to-seek timeline and incident markers, one main camera that follows the selected incident plus a filmstrip (tiles swap without reloading video; live detection counts, box key, evidence labels in plain words), incident panel with response progress (signals -> opened by ARGUS -> human decision), risk gauge, collapsible score breakdown and hash-chained decision log, Respond menu (recommended action, acknowledge, dispatch guard, escalate, notify police, dismiss as false alarm; extra actions recorded as audit notes), Ask ARGUS moved to a header popover (/), raw signals collapsed to a ticker, status symbols with shape + colour, source icons, responsive down to phone width; overlay redraws only on new frames, mock data lazy-loaded (main bundle 337 -> 318 kB); demo script and pitch updated for the new controls
71f853c door_eval.py: per-camera door-sensor scoring with overrides; HANDOFF: door findings (G331 doors held open vs opening labels, G336 door 100 m away, rejected occlusion idea)
958d9de Evidence stills for uploaded videos: the worker renders them from the original clip (rules canvas mapped back to the clip's frames and pixels; never fails a job), GET /api/uploads/{job}/thumbs/{event}.jpg, a key frame on each upload incident and a still on each event; Still is a shared component
7ed1a3b HANDOFF Â§11 update: set A result and why it missed, set C, merged report, timing, Ask offline warm-up
```
