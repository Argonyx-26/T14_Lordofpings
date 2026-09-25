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

The shot list and voice-over are in `docs/PITCH.md` §4.

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
  - The bus incident is titled "Unattended object". On stage, say **"an unattended object, then it changes hands"**.
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
