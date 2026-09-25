# HANDOFF: Tanush → Jack (demo laptop), Fri 25 Sep, 16:35 IST

Everything below is on `main`. It covers what changed on my side since your `HANDOFF.md` (16:16), and
**everything left to do on your laptop, in order**. Thanks for the camera-wall fix (b4284fc): the run-sheet stays
at **10×**.

**Deadlines:** feature freeze **22:00** · 2-minute video recorded by **07:00** · **code freeze 09:00** · then
5 timed rehearsals (one with Wi-Fi off). Ask the organisers for our exact pitch slot if nobody has yet.

---

## 0. TL;DR: do these in order

1. `git pull`, then re-run `scripts\setup_windows.ps1` (installs the new Python packages and `yolo11m.pt`, rebuilds the console, runs tests). §2
2. `scripts\run_demo.ps1 -Prepare -Live`: rebuilds everything; your cached Gemini briefs stay. §2
3. Test **Analyse a video** with two real clips and send me the results. §3
4. Replace the sample screenshot on the project website with a real one. §4
5. Record the **2-minute demo video** by 07:00. §5
6. Wi-Fi off: full run-through of the demo. §6
7. Learn your speaking part (slides 5 and 6). §7

---

## 1. What changed on my side since your handoff

| What | Where | Notes |
|---|---|---|
| **Analyse any video** (new feature) | `backend/argus/uploads.py`, `/api/uploads*` in `api/main.py`, `frontend/src/components/UploadView.tsx` | "Analyse a video" button, top right of the console. Upload any MP4/AVI/MOV/MKV/WebM, up to 2 GB. It runs **YOLO11s + ByteTrack**, then **your valuables pass** (yolo11m @ 1280, conf 0.1), then **your `ClipRules` unchanged**, then fusion. The review screen shows the video with detection boxes, a clickable event timeline and incidents. Details in §3. |
| New Python deps | `backend/requirements.txt` | `python-multipart` (uploads) and `lap` (ByteTrack; without it ultralytics downloads it at runtime, which breaks offline). |
| `yolo11m.pt` fetched by setup | `scripts/setup_windows.ps1` | You probably already have it in `models\` from `run_bags.py`. |
| New fusion area `upload` | `backend/argus/config/site.yaml` | "Uploaded clip", criticality 0.6, no GPS geometry. |
| **Project website** | `site/` | Served by the backend at **http://localhost:8000/site/**. Offline: fonts bundled, no analytics tag, **not deployed anywhere**. |
| Prepare-step order fix | `scripts/run_demo.ps1` | `npm install` now runs before `npm run build` (your issue #2). It also prints the site URL. |
| Console link param | `frontend/src/App.tsx` | `http://localhost:8000/?incident=INC-0007` opens with that incident selected. Useful for screenshots. |
| Pitch pack | `docs/PITCH.md` | Your measured numbers, 10× run-sheet, no pilot. Your Gemini wording is kept. |
| **Deck** (8 slides) | private link, I'll share it with you | Updated with your numbers, "Gemini writes the brief", 10× in the Live slide's notes, and a closing slide about analysing any footage (no pilot). Speaker notes hold each person's script. |
| Tests | `backend/tests/` | **25 pass** on my Mac. New: `test_uploads.py`, plus a test that the site is served. |

I haven't touched anything under `backend/argus/vision/`; uploads only import `ClipRules` from it.

---

## 2. Update the laptop

```powershell
cd C:\argus
git pull
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1 -Prepare -Live
```

- Setup skips what's already done: it won't reinstall CUDA torch if CUDA works.
- `-Prepare` skips cached tracking, bags and doors, then reruns rules, MP4s (full + your 5 fps proxies), eval, briefs (cache hits) and the console build.
- Check the console at http://localhost:8000 and the site at http://localhost:8000/site/.

If setup fails anywhere, the minimum is:
`.venv\Scripts\python -m pip install -r backend\requirements.txt`, then `npm --prefix frontend install`,
then `npm --prefix frontend run build`.

---

## 3. Test "Analyse a video" on the GPU (please send me the results)

I could only test this on my Mac's CPU, **without** the valuables pass, on cropped clips. That got real tracking
(7,815 detections on a 45 s bus-station crop), correct boxes and a working review screen, but no incidents. It has
**never run on the GPU with the full pipeline.**

1. Console → **Analyse a video** → upload the full clip
   `data\meva\video\2018-03-15.15-15-00.15-20-00.bus.G331.avi`.
   - Expected: an **abandoned object** around **3:07–3:30** into the clip (ground truth 15:18:07 = 3:07).
2. Then upload `data\meva\video\2018-03-15.14-50-00.14-55-00.school.G421.avi` (the cafe).
   - Ground-truth thefts at **3:38** and **4:18**.
   - **Expect some extra bag alerts here:** uploads use no camera polygons, so your cafe `bag_ignore` (snack counter, bin) doesn't apply. That's the honest limit of zone-free analysis. Just tell me how many.
3. Note for each clip: **total time**, whether the expected incident appears, and any errors. The job's folder is `data\uploads\<id>\` (`job.json`, `result.json`).

**How it works, in case something breaks:**
- Each upload gets a MEVA-style clip name (`2000-01-01.00-00-00.<end>.upload.U<id>`) so `ClipRules` can parse it.
- Frames are re-timed onto your 30 fps / stride-2 clock (even frame numbers), whatever the source fps is.
- Boxes are scaled to your 1920×1072 canvas, so `FRAME_W/H` edge checks hold.
- The browser MP4 is made with ffmpeg, in parallel with tracking.
- Jobs run one at a time on a single worker thread, and survive a backend restart (unfinished ones are marked failed).
- For a quick CPU test: `ARGUS_UPLOAD_BAG_PASS=0` skips the valuables pass.
- `data\uploads\` is gitignored. Delete a job by deleting its folder.

**Stage use:** optional. If a judge asks "does it work on other footage?", upload a short clip (under a minute of
footage so it finishes in time). Don't put it in the 5-minute pitch.

---

## 4. Project website: one real screenshot

The console image on the site is currently from sample-data mode, and its caption says so.

1. Run the full replay, open the bus-station incident, then press `Win + Shift + S`.
2. Save the capture as `site\assets\console-preview.jpg`, about 1536 px wide.
3. In `site\index.html`, delete the sentence "This preview uses the console's sample-data mode; the live demo runs on the full MEVA replay." (the caption under that image).
4. The team section lists you as "Vision pipeline and demo laptop" and Utkarsh and Ojus as "Team member". Fix the roles if needed.
5. Commit and push. The site is only ever shown from your laptop: http://localhost:8000/site/, or double-click `site\index.html`.

---

## 5. Record the 2-minute demo video (deliverable + stage backup), by 07:00

The full script (prep, shot list, voice-over, editing steps) is in **`docs/DEMO_VIDEO_SCRIPT.md`**.

- **Recording:** Xbox Game Bar (`Win + Alt + R`) with the console full-screen (F11), at **10×**.
- **Editing:** trim in Clipchamp. Add auto-captions; judges may watch it muted.
- **The results card at 1:45:** 4 of 5 caught · 0 false incidents · 1,242 → 20 → 3 · 30 fps.
- **Copies:** one on the desktop, one on a USB stick, and send one to me.

---

## 6. Offline run-through and stage checklist

- Wi-Fi off, `scripts\run_demo.ps1 -Live`, then walk the run-sheet (`docs/PITCH.md` §3) end to end, twice.
- Charger in, power mode **Best performance**, **Energy Saver off**, sleep **Never**. Close Roblox, Steam and the Discord overlay.
- `.env` holds `GEMINI_API_KEY` (never commit it). The briefs are cached, so no internet is needed.
- Run-sheet notes:
  - The bus incident is now titled **"Possible theft: unattended object taken"** (see §12); no stage workaround needed.
  - Stay at **10×**; at 20× it reaches only about 18× and jumps to catch up.
- If anything breaks on stage, say "let me show you the recording" and play the backup video. Never debug live.
- `scripts\stop_demo.ps1` stops everything.

---

## 7. Your speaking part (C): slides 5–6, 3:15–3:55

The full script is in the deck's speaker notes and in `docs/PITCH.md` §2. Key lines:

- **Slide 5, How it works:**
  - Every stream is real: MEVA multi-camera footage and GPS.
  - YOLO11 and ByteTrack run on this laptop's GPU, and the rules need no training and no labels.
  - Fusion counts each source once, and bursts of the same alert count as one common cause.
  - The score is transparent.
  - Gemini writes the brief, but it can't create or hide an incident; we reject any sentence the evidence doesn't back.
- **Slide 6, Results:**
  - 4 of 5 caught; the miss is the black purse on the black bench.
  - 2 stray camera bag alerts, but 0 false incidents.
  - Siloed thresholds would page 20 times; Argus raises 3.
  - Door sensor 0.54 / 0.75 on indoor doors.
  - 30 fps live on this laptop.
- **Q&A you'll likely take:** the miss; staged data; how the door stream works; scale. Answers are in `docs/PITCH.md` §5.

---

## 8. Optional, only if time and internet allow (before 22:00)

- Your Gemini jargon fix: one line in the `SYSTEM` prompt, e.g. *"refer to device-location signals as people's phones showing a crowd gathering or leaving; avoid internal type names"*. Then delete `data\cache\briefs.json` and run `-Prepare` **online**. Skip it if there's any risk to the cache.

## 9. Ground rules (unchanged)

- Always `git pull --rebase` before pushing. No `data/`, video, weights or `.env` in git.
- My side doesn't edit `backend/argus/vision/`; yours doesn't need to edit `uploads.py`. If you do, tell me.
- Theft and abandonment labels stay eval-only, and uploads never read annotations.
- Anything you change, add a line to your `HANDOFF.md` so the pitch and deck stay in sync.

---

## 10. Update 17:10: your §9 upload results

- **Night-factor bug fixed:** uploads are now stamped at **12:00** on the synthetic day, so they always score with `time_factor` 1.0 (test added). Thanks for catching it.
- **Heads-up:** your bus upload's 72 included the ×1.3 night factor. Without it, the same single-camera abandonment scores about **55**, exactly the open threshold, so it still opens, but only just. I've left the scoring alone rather than tune it to pass. For a venue clip on stage, your advice stands: film a clear abandonment (owner out of frame for 15 s or more).
- Old analyses in `data\uploads\` keep their midnight stamp; re-upload a clip to see the new score.

---

## 11. Update 17:40: full-codebase review (nothing in `backend/argus/vision/` changed)

- **Backend API (`api/main.py`):**
  - The replay loop now survives any failed tick, which is logged instead of silently stopping the demo.
  - Broadcasts iterate a snapshot of the connected clients.
  - Read endpoints (`/api/state`, `/api/incidents/*`, `/health`, `/config`, `/audit`, `/metrics`) run on the event loop, so they can't race the replay.
  - Brief tasks are kept referenced.
  - The recent-events buffer stays bounded on forward seeks.
- **Uploads:**
  - The job manager is created once, even under concurrent first requests.
  - A failed ffmpeg encode no longer leaves a half-written `web.mp4`; the original file is served instead.
  - The duration falls back to the decoded length when a container has no frame count.
- **Dead code removed:** `gpx_slot_names`, `RULES_FPS`, the engine's unused `now` and `incidents_opened`, and an unused import in `brief/llm.py`.
- **`scripts/transcode.ps1` is now repo-relative** (it was hard-coded to `C:\argus`), and the `draw_zones.py` docstring points at `vision/zones.yaml`. Both are your files: small, safe changes.
- **Verified:** 26 tests pass; `tsc` is clean with unused checks; the console builds. A live smoke test ran WebSocket ticks at 30×, 60 concurrent reads during replay, forward and backward seeks, and client churn, with no errors. The upload pipeline ran end to end again.
- **After `git pull`:** restart the backend (`scripts\run_demo.ps1`). No re-prepare is needed.

---

## 12. Update 18:40: winning-polish round (please read, then run §12.3 tonight)

### 12.1 What changed (nothing in `backend/argus/vision/` was edited)
- **Story titles:** when an incident holds both `abandoned_object` and `custody_change`, its title is
  **"Possible theft: unattended object taken"** (playbook `stories`). The template brief matches it. Single-signal
  titles are unchanged.
- **Decisive signals:** an `abandoned_object` at severity ≥ 0.8 and confidence ≥ 0.6 (owner walked out of view) opens an
  incident on its own, whatever the score (playbook `decisive`, incident field `decisive`, explained in the console).
  This fixes uploads sitting exactly on 55. On the demo replay it should change nothing: the abandonment incident was
  already open, and your two stray alerts are `custody_change`. **Please confirm with the test below.**
- **Quick scan for uploads:** an optional tick-box skips the valuables pass (about 2× faster) for short Q&A clips.
- **Evaluation:** `score_window()` is shared by the tuning-window and held-out evaluations. It now reports
  `false_incidents` (opened incidents with no staged event nearby) and the door metric split into indoor vs all cameras.
  Decisive openings count as "alerted".
- **Tests (now 35 backend + 8 frontend):**
  - `tests/test_vision_rules.py` pins your rules on synthetic tracks: owner walks out → `abandoned_object` at 0.8;
    a stranger carries the bag off → `custody_change`; a seated owner → nothing; walking vs sprinting.
  - `tests/test_headline.py` runs only on your laptop: it asserts ≥ 4/5 caught, 0 false incidents and ≤ 5 incidents
    on the real events.
  - Frontend tests: `npm --prefix frontend test`.

### 12.2 After `git pull`
```powershell
.venv\Scripts\python -m pip install -r backend\requirements.txt
cd backend; ..\.venv\Scripts\python -m pytest -q; ..\.venv\Scripts\python -m argus.eval.evaluate; cd ..
powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1 -Live
```
`test_headline.py` must pass on your laptop. If it doesn't, tell me the failure before changing anything.

### 12.3 The held-out run (the answer to "isn't it overfitted?"), about 2 h on the GPU
```powershell
cd backend; ..\.venv\Scripts\python -m argus.eval.holdout --set A; cd ..    # ~55 min: a different day, has 1 staged theft
cd backend; ..\.venv\Scripts\python -m argus.eval.holdout --set B; cd ..    # ~60 min: later window, all 6 cameras + GPS
```
- The unchanged pipeline (your exact `run_tracks.run`, `run_bags.run`, door sensor and `ClipRules`) runs on footage
  never used for tuning.
- Everything goes under `data_holdout/`, so the demo data is untouched. Clips already done are skipped, so it can be
  stopped and resumed.
- It writes **`docs/HOLDOUT_RESULTS.md`**. Commit and push that file; I'll put the numbers on the results slide and
  the site.
- Run A first (it contains the one staged theft outside our window). Don't run it while recording the video: the GPU
  is shared with the live tile.

### 12.4 Door sensor: what I tried (no action needed)
The all-camera door precision (0.21) comes almost entirely from the exteriors. I ran the door sensor offline on the
bus (G331) and plaza (G638) clips from the tuning window:

| Camera | Rule | Detected | Correct | Truth | Precision | Recall |
|---|---|---|---|---|---|---|
| G331 bus | current | 23 (door_b 13, door 7, door_r 3) | 1 | 1 | 0.04 | 1.00 |
| G331 bus | "pass-through" (person must cross the door line) | 9 | 0 | 1 | 0.00 | 0.00 |
| G638 plaza | current | 14 | 6 | 11 | 0.43 | 0.55 |
| G638 plaza | "pass-through" | 12 | 4 | 11 | 0.33 | 0.36 |

- At the bus station, most false openings are `door_b`: the ATM queue stands in front of it.
- The stricter rule was worse on both cameras, so I didn't ship it.
- On stage, quote the indoor number (0.54 / 0.75) and say the exteriors are a motion heuristic (PITCH §5 has the answer).
- If you want to try one thing: narrow the `door_b` polygon for G331 in `backend/argus/vision/zones.yaml` so it covers only the door leaf, not the
  queue. That file is yours, so it's your call.


## 13. Update 21:30: new console, please retake the site screenshot

The console was redesigned (commit `acf0e5f`, frontend only: nothing in `backend/` changed). One main camera follows
the selected incident, with the other cameras in a strip below it. A band at the top shows the situation, the
signals-to-decisions funnel and the ground-truth score. Actions are now under **Respond ▾**.
`docs/PITCH.md` and `docs/DEMO_VIDEO_SCRIPT.md` already name the new controls.

The screenshot on the site still shows the old console. It needs your laptop, because mine has no footage or camera
events.

1. `git pull`, then `scripts\run_demo.ps1 -Prepare` (it rebuilds the console). Start the demo as usual.
2. Put the replay at 15:18:40, paused (the same moment as the current shot):
   ```powershell
   Invoke-RestMethod -Method Post http://localhost:8000/api/replay -ContentType application/json -Body '{"cmd":"pause"}'
   Invoke-RestMethod -Method Post http://localhost:8000/api/replay -ContentType application/json -Body '{"cmd":"seek","value":1521141520}'
   ```
3. Open http://localhost:8000/?incident=INC-0007 in a 1536×864 window. If the bus-station incident has another id now,
   just click it in the Incidents list. Check that:
   - the main camera is G331 with real footage and detection boxes;
   - the incident panel shows the Gemini brief (not "from the scoring template").
4. Capture it with `Win + Shift + S`, or headless Chrome as last time. Save it over `site\assets\console-preview.jpg`,
   1536×864. If the footage comes out black, take the shot by hand instead.
5. In `site\index.html`, update the image's alt text and the caption under it to describe the new console, for example:
   - alt: "The Argus console: situation band and signal funnel, the bus-station camera with detections, ranked incidents, a to-scale site map, and the incident's brief and response progress"
   - caption: "The Argus console at 15:18 in the MEVA replay: the bus-station incident is on the main camera, with its brief, recommended action and response progress."
6. Commit and push.

## 14. Update 23:15: forecasting, threat assessment for uploads, README / CI / Pages

Pushed by Tanush (nothing in `backend/argus/vision/` changed). After `git pull`, `scripts\run_demo.ps1 -Prepare` rebuilds the console.

- **"Where this is heading" + response planner** (`backend/argus/forecast.py`, `GET /api/incidents/{id}/forecast`): crime-script stage, what would change the score (the real scorer on real evidence plus one hypothetical signal), and a course-of-action comparison you can simulate and apply. Guard posts and police/medical times are assumptions in `site.yaml → response`; check that the two guard posts look sensible on the site map.
- **Analyse a video is now a threat assessment**: verdict, risk over the clip, a profile switch (Airport / School / Park, re-assessed instantly via `GET /api/uploads/{id}/assess`), and a forecast + planner per incident.
- **Please capture one screenshot for the README**: open your analysed `2018-03-15.15-15-00.15-20-00.bus.G331.avi` upload (the one with incident 72) at 1600×1000 with `http://localhost:8000/?upload=<job id>`, save it as `docs/readme/upload.png`, and add under point 5 of "What ARGUS does" in `README.md`:
  `<p align="center"><img src="docs/readme/upload.png" alt="Threat assessment of an uploaded bus-station clip" width="100%" /></p>`
  (On my Mac the only real clip was a 45 s excerpt with nothing staged in it, which correctly came back "No threat found".)
- **CI** (`.github/workflows/ci.yml`): backend pytest + frontend lint, types, tests, build on every push.
- **Website hosting**: no admin access, so no GitHub Pages. The site is **live at https://argus-lordofpings.vercel.app** (judges' page `/judges.html`, offline console demo `/console/`, Raah analytics working). `scripts/deploy_site.sh` republishes it from Tanush's Mac. The demo laptop is unaffected: everything there stays offline.

## 15. Update 02:30: pull, rebuild the console, run it with your live camera

The redesigned console (the ARGUS eye, boot sequence, forecast + response planner, upload threat assessment) is on
`main`, and your stage-camera change sits on top of it. `run_demo.ps1` now takes the camera directly.

**1. Stop what is running, then pull**
```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop_demo.ps1
git pull
```

**2. Rebuild the console** (it has a new package, `motion`, so install first). Quick path, when the pipeline data hasn't changed:
```powershell
npm --prefix frontend install --no-audit --no-fund
npm --prefix frontend run build
```
(`scripts\run_demo.ps1 -Prepare` does the same and also re-runs rules, MP4s, eval and briefs; use it if you changed vision outputs.)

**3. Start the demo with the live camera and the stage bag rule**
```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1 -Camera 0
```
- `-Camera 0` = webcam 0 (`1` for a USB camera; DroidCam: `-Camera http://<phone-ip>:4747/video`). It implies `-Live` and turns on `--rules`.
- Or, to show your trained weapon model on the live tile instead: `-Camera 0 -LiveWeights models\weapons_yolo11s.pt`.
  The bag rule is off in that mode (it needs the people-and-bags detector), so pick one for the stage. Suggestion: bag rule live,
  weapons through **Analyse a video** with a short staged clip (as in §12).

**4. Open the console:** http://localhost:8000, then **Ctrl+Shift+R** once so the browser drops the old build.
- First load in a tab plays the boot (the eye opens, then flies into the top band; about 2 s, "skip" at the bottom). It shows once per tab session.
- Camera header → **Live inference** shows the live feed. When someone leaves a bag for 15 s, the incident appears in the queue,
  the console switches to the live feed for it, and **Where this is heading → Plan the response** works on it like any other incident.
- Live tile check: http://localhost:8001/live/stats should show ~30 fps with Energy Saver off.

**5. Quick checks before stage**
- Incident panel: *Where this is heading* card and *Plan the response* open; *Respond* records to the audit log.
- Analyse a video: open an analysed clip, switch Airport / School / Park, open *Plan the response* on a flagged incident.
- Wi-Fi off once (§6): the console, boot and site must work with no network (they do on my side; nothing loads from the internet).

CI note: your agent test needed OpenCV on the CI machine; CI now installs `opencv-python-headless`. Nothing changes on the laptop.

## 16. Update 05:00: the intel layer (patterns, near-repeat watch, blind spots, case report, camera tamper)

Answer to the round-1 feedback ("very little innovation"): a read-only layer **above incidents**. It never changes a
score, opens or hides an incident, so the 4/5, 0-false numbers are untouched. Plan and research: `docs/INNOVATION.md`;
pitch beats and Q&A: `docs/PITCH.md` §0. **Nothing in the vision pipeline changed except one new live rule (`--tamper`).**

**1. Stop, pull, rebuild** (no new npm packages)
```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop_demo.ps1
git pull
npm --prefix frontend run build
```

**2. Measure it on the real events (this is the number for the pitch), then paste the output into the team chat**
```powershell
cd backend
..\.venv\Scripts\python -m argus.eval.patterns_eval
```
It prints how many later staged events were in a *watch next* area one second before they began (with the chance
level), and which staged incidents ended up linked in a series. On my Mac there is no `cctv.jsonl`, so I only
checked it on synthetic events at MEVA's staged times: the real numbers can differ, and only yours go in the pitch.

**3. Give the hosted console (Vercel, `?mock`) the real incidents and the intel**, then commit and push the snapshot
```powershell
..\.venv\Scripts\python -m argus.export_snapshot
cd ..
git add frontend/src/mock/snapshot.json
git commit -m "Offline demo snapshot from the real replay (incidents, evidence, forecasts, intel)"
git push
```
(The current snapshot is from Friday 23:10 with 2 camera signals; the exporter refuses to overwrite it with fewer.)

**4. Start the demo as before** (`scripts\run_demo.ps1 -Camera 0`). `-Camera` now also passes `--tamper`.

**5. What to check in the console** (http://localhost:8000, Ctrl+Shift+R once)
- Play from the start. After the cafe theft opens, the **Site** map outlines the *watch next* areas (dashed blue) and
  hatches **Parking** ("no camera"); the legend shows *visibility %* and the minutes left.
- When the bus-station theft opens: the queue tags both incidents **pattern 1/2, 2/2**, the map draws an arc between the
  areas, and the incident panel has **Part of a pattern** (a chain, each link's reason: *walkable*, *same place* or
  *too soon to walk*).
- **Why this score** ends with *What could agree here* (streams covering the area, how many agreed, the ceiling).
- Footer of the incident panel: **Case report** (print / save as PDF, or copy as text).
- Ask ARGUS: "Are these thefts connected?" answers from the links (offline too: the template answers it).
- Stage camera: hold a hand over the lens for 3 s. The stream gets a red border and "CAMERA VIEW LOST", an incident
  **Camera view lost** opens at once (decisive in every profile), and the live area goes blind on the map until the view
  is back ("Camera view restored" joins the same incident with how long it was gone). If it fires on your venue's
  lighting without a hand, tell me: thresholds are `FLAT_STD` / `DARK_MEAN` / `BLUR_FRAC` in `vision/live_rules.py`.

**Not changed on purpose:** the investigator agent's tools (a new tool changes its cache key and would drop your
rehearsed runs).
