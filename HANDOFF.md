# HANDOFF: vision side → Tanush (state as of Fri 25 Sep 2026, evening)

From Mohit (vision + demo laptop). Written so Tanush, or his Claude, can pick up from here without asking.
Everything below is on `main`. The demo laptop is the Windows RTX 5060 machine; `data/` and `.env` live only there.

## 1. What changed today (commits on `main`)

| Commit | What |
|---|---|
| `ce17e4d` | `live.py`: no burned-in header by default (the console draws its own from `/live/stats`); `--header` for standalone use. |
| `7c68c17` | README **"How the vision works"** section with measured numbers. `live.py` opts out of Windows background power throttling. `RUN_WINDOWS.md` checklist: Energy Saver off. `PITCH.md` placeholder table: vision rows filled. |
| `5f6df65` | **Briefs can use Gemini.** `docs/PITCH.md`, README and `RUN_WINDOWS.md` now say Gemini instead of Claude. |
| this commit | This file. `run_demo.ps1` brief step label mentions `GEMINI_API_KEY`. |

## 2. LLM briefs now use Gemini. **The pitch wording changed.**

We have no Anthropic key, so the brief uses Gemini. The Claude path is untouched.

- `backend/argus/brief/llm.py`:
  - `PROVIDER` is `"claude"` if `ANTHROPIC_API_KEY` is set, else `"gemini"` if `GEMINI_API_KEY` (or `GOOGLE_API_KEY`) is set, else `None` (template only).
  - Gemini is called over **REST with `httpx`** (`generateContent` + `responseSchema`). There is no new dependency; `pip install google-genai` timed out on the laptop and wasn't worth the risk.
  - Model: `ARGUS_GEMINI_MODEL`, default `gemini-flash-latest`. `MODEL` (shown in `/api/health`) follows the provider.
  - **Same guardrails as the Claude path:** output goes through `validate()` (the action must be in the playbook, every cited evidence ID must belong to the incident, and no other area may be named). Any failure (offline, HTTP error, blocked or malformed output) returns `None`, so the template takes over.
- `schema.py`: `Brief.model: str | None = None` records which LLM wrote the brief. `frontend/src/types.ts` mirrors it.
- `IncidentDetail.tsx`: the label reads "written by Gemini" or "written by Claude", depending on `brief.model`.
- **Tested with the real key:** one brief in ~6 s, which passed validation. `run_demo.ps1 -Prepare -Live` then cached **7 briefs** in `data/cache/briefs.json` (the cache key is area + evidence IDs, so one brief per incident stage). With those cached, the demo is offline-safe.
- **`docs/PITCH.md`: 4 lines changed from "Claude" to "Gemini":** the slide 5 row, speaker C's script, the video voice-over at 0:50, and the Q&A answer "Does the LLM hallucinate threats?". **Update the actual slides and speaker notes to match.**
- Nice to have: Gemini sometimes writes stream jargon like "device dispersal" or "device crowding". One line in `SYSTEM`, such as *"Refer to device-location signals as people's phones showing a crowd gathering or leaving; avoid internal type names"*, plus deleting `briefs.json` and re-running `-Prepare` with internet would fix it.

## 3. Measured numbers (quote these; source is `data/cache/metrics.json` + `vision/tune.py`)

MEVA 2018-03-15 14:50–15:20, 6 cameras, 9 clips.

| Metric | Value | Notes |
|---|---|---|
| Staged incidents caught | **4 / 5** | Cafe thefts at 14:53:38 and 14:54:18, bus theft at 15:13:30, bus abandonment at 15:18:07. |
| Miss | G331 theft 14:56:54 | Black purse on a black bench; the detector never sees it. `static_change.py` finds it but is off (+12 false alarms). |
| False incidents | **0** | Traced: 2 camera-level bag alerts are away from ground truth. `cctv-G638-000014` sits in plaza candidate INC-0001 (score 26, below watch 35); `cctv-G331-000059` folded into the true bus incident INC-0007. |
| Funnel | 1,242 raw → 20 siloed alerts → **3 incidents** | 99.8 % reduction. |
| Door sensor, indoor (G419/G420/G421, door-leaf method) | **P 0.54 · R 0.75** | ±2 s against MEVA door-open annotations. |
| Door sensor, all 6 cameras | P 0.21 · R 0.52 | G331/G638 use the feet-in-door-zone heuristic; G331 fires on the ATM queue (64 detections, 1 annotated opening). |
| Live tile | **30 fps** (the clip's real-time cap), 13–23 ms/frame | YOLO11s @960 FP16 + ByteTrack. **Energy Saver must be off**: with it on, 16–19 fps (23–27 after the throttling opt-out). |

**Retractions of things Mohit said earlier:**
- **"Door precision 0.50" is not defensible.** It is the precision with G331 left out. G331's annotations are not missing; its detections are real false positives (checked: the door-leaf method does even worse there, 93 detections and 0 true positives, so it was reverted). Quote indoor 0.54 / 0.75, or overall 0.21 / 0.52.
- **Drop the suggestion to "skip G331 in the door metric"**, for the same reason.
- The suggestion that the **bus incident title comes from the first signal** was wrong. `FusionEngine._title` already uses the highest-severity signal. The bus incident reads "Unattended object" because `abandoned_object` is severity 0.8, while `custody_change` is 0.45 (0.6 if the carrier exits). If you want it to read as a theft, either rank by type in `_title`, or say "unattended object, then custody change" on stage.

## 4. Verified on the demo laptop today

- `scripts\run_demo.ps1 -Prepare -Live` runs end to end: it skips cached tracking, bags and doors, then runs rules, MP4s, eval, the Gemini briefs and the console build, then starts the backend and the live tile.
- Full 30-minute replay without errors:
  - Cafe incident "Object changed hands" at 14:53:41: score 48 (Watch), rising to 68 (High) with GPS evidence.
  - Bus station incident at 84 (Critical), ranked 1.
  - Abandonment incident at 61.
  - Score breakdown and Escalate / Acknowledge / Dismiss work. The site map glows on each incident.
- Backend tests: 21 passed. Frontend: `tsc` clean, `vite build` OK.

## 5. Open issues

1. **FIXED (Mohit): the camera wall stuttered at 2× / 5× / 10×, and boxes drifted off people at 5×.** The live tile was never the problem (29.7 fps produced and 29.7 fps received by a client).
   - **Cause 1, sync loop:** `Tile` seeked whenever drift was over 1.5 s. Each 0.25 s tick moves the clock 1.25–2.5 s at 5–10×, so it re-seeked every tick. With ~8 s GOPs a seek never finished before the next one, and `play()` was interrupted, so tiles sat paused mid-seek: a slideshow (468 seeks in 20 s at 10×).
   - **Cause 2, decode load:** 6 tiles × 30 fps × 10× = 1,800 decoded frames/s. Measured on 6 bare `<video>` elements: 1×, 2× and 5× are fine (60 fps shown), but 10× collapses to 0.2× and 16× freezes.
   - **Cause 3, boxes:** boxes were drawn at `currentTime`, which runs ahead of the frame actually on screen when the decoder lags.
   - **Fix in `CameraWall.tsx`:**
     - Never seek while a seek is in flight. The tolerance is `max(2 s, speed × 1 s)` while playing, and small drift is absorbed by nudging `playbackRate` ±30 %.
     - From **4×** up, tiles play a **5 fps proxy** (`/media/fast/<stem>.mp4`; falls back to the full MP4 on error).
     - Boxes are drawn at the presented frame's `mediaTime` (`requestVideoFrameCallback`).
   - **Fix in the media:** full MP4s re-encoded with 1 s keyframes (`-g 30`). Proxies are `fps=5`, `-g 5`, under `data/meva/web/fast/`. `run_demo.ps1` (MP4 step) and `transcode.ps1` make both.
   - **Measured in the console after the fix** (browser pane visible, 6 tiles):

     | Speed | Achieved | Seeks | Playing |
     |---|---|---|---|
     | 2× | 2.0× | 0 | 100 % |
     | 5× | 4.8× | 0 | 100 % |
     | 10× | 9.7× (= the clock's own 9.75×) | only the switch to the proxy | 100 % |
     | 20× | ≈18× | a catch-up seek every ~2.5 s | |

     Chrome caps `playbackRate` at 16, so 20× can't play continuously.
   - **Heads-up: the replay clock runs ~2.5 % slow** (9.75× at 10×). `_loop` in `api/main.py` does `advance(TICK_S)` after `sleep(TICK_S)`, ignoring the real elapsed time. It's harmless, but `advance(elapsed)` with `time.monotonic()` would make it exact.
2. ~~`run_demo.ps1 -Prepare` built the console before `npm install`~~: fixed by Tanush in `a28ae32`.
3. ~~PITCH run-sheet said 20×~~: changed to 10× by Tanush in `a28ae32`. Keep 10×.

## 6. Before going on stage (demo laptop)

- Charger in, Windows power mode **Best performance**, **Energy Saver off**, sleep **Never**. Close Roblox, Steam, and the Discord overlay.
- `.env` in the repo root holds `GEMINI_API_KEY` (gitignored; never commit it). The briefs are already cached, so no internet is needed on stage.
- Once: Wi-Fi off, then `scripts\run_demo.ps1 -Live`, to prove the demo works offline. Stop it with `scripts\stop_demo.ps1`.
- Console at http://localhost:8000, live tile at http://localhost:8001/live.mjpg.

## 7. Ground rules (unchanged)

- Theft and abandonment annotations are **eval only**. Nothing under `backend/argus/vision/` reads them; only `eval/evaluate.py` does.
- No video, weights, keys or `data/` in git. Only the `.pt` weights came from Skylinev2; no code did.
- Shared backend code stays cross-platform (Tanush is on a Mac). Windows-only calls live only in vision scripts, guarded by `sys.platform` (e.g. `live.py`'s `no_power_throttling()`).

## 8. Update: Fri 25 Sep evening, after `HANDOFF_TO_JACK.md` (your §2 and §8 done)

- **§8 Gemini jargon fix: done.** `SYSTEM` in `brief/llm.py` now says to write for a guard, never use internal type names, describe device-location evidence as "people's phones show a crowd gathering or leaving", and describe a custody change as "a bag changed hands". The old cache was backed up; all **7 briefs were regenerated online, with 0 template fallbacks**. For example: *"A suitcase has been left unattended at the bus platform while people's phones show a crowd gathering at the bus station."*
- `brief/warm.py`: the "no key" warning is now provider-aware. It used to say `ANTHROPIC_API_KEY is not set` even when Gemini was working.
- **§2 done on the demo laptop.**
  - `setup_windows.ps1` passed 7/7, with **25 tests passing**.
  - `run_demo.ps1 -Prepare -Live` ran end to end, and the site is at `/site/`.
  - Fix needed on the way: this `.venv` was created by `uv`, so it has **no pip**, and `setup_windows.ps1` would have failed at `pip install`. The script now runs `python -m ensurepip --upgrade` first (one line). `python-multipart` was installed; `lap` 0.5.13 was already there.
- Next on this laptop: **§3 Analyse a video** on the GPU, then the website screenshot, the 2-minute video, and the offline run-through.

## 9. §3 "Analyse a video": GPU results (full pipeline, live tile running at the same time)

| Clip | Time | Events | Incidents | vs ground truth / demo pipeline |
|---|---|---|---|---|
| `15-15-00.15-20-00.bus.G331` (5:00, 1080p30) | **318 s** (tracking 147 s + valuables 162 s + rules 5 s) | 7 occupancy, 2 `abandoned_object` (backpack) at **3:26.6 and 3:46.0** | **1: "Unattended object", score 72, open** | GT 3:07. The events are identical to the demo pipeline (3:26.6 / 3:46.0). No errors. |
| `14-50-00.14-55-00.school.G421` cafe (5:00) | **298 s** | 8 occupancy, 1 `custody_change` (laptop) at **4:19.9**, sev 0.45 | **0** | Theft 2 (GT 4:18) detected; **theft 1 (GT 3:38) missed**. The demo pipeline finds it at 3:41 with sev 0.6, the "carrier exits through a door" variant, which needs the camera's door polygons. **No extra bag alerts**, contrary to the expectation. |

- **Speed ≈ 1× real time** (a 1-min clip takes ~1 min). Only clips of ~30 s or less fit in Q&A.
- **Why the cafe hit didn't become an incident:** a single source at sev 0.45 scores **33**, just under watch (35). Breakdown: confidence 0.35, criticality 0.84, `time_factor` **1.3**.
- **Bug-ish, for Tanush:** uploads are stamped `2000-01-01 00:00`, so they get the **night** factor (20:00–06:00). Probably unintended: either stamp uploads at midday, or skip the night factor for the `upload` area.
- **For a venue clip on stage, film an abandonment** (a bag left behind while its owner walks out of frame for 15 s or more). That's sev 0.8 and opens an incident on its own. A bag hand-off alone (0.45) won't, unless it's followed by the carrier walking out of frame.

## 10. §4 Website screenshot: done

- `site/assets/console-preview.jpg` is now a real capture (1536×864) at 15:18:40 in the MEVA replay, taken with headless Chrome at `/?incident=INC-0007`:
  - the bus-station incident is open, with its Gemini brief and score breakdown;
  - all 3 incidents are listed;
  - the G331 tile shows real footage with detection boxes.
- The five school tiles read "No recording at this moment", which is true at 15:18: those clips end at 14:55.
- The "sample-data mode" caption is replaced with a factual one.
- **Team: Utkarsh and Ojus didn't come, so Jack asked to remove them.** The site's team section now lists Tanush and Mohit only, in a 2-column grid.
- **Pitch impact (Tanush):** `docs/PITCH.md` assumes four speakers (A lead, B demo driver, C vision, D business). With two of you, split it as **Tanush = A + D** (problem, business, close) and **Jack = B + C** (drives the live demo, then slides 5–6). Update the deck's speaker notes to match. Also check whether the rule that every member speaks needs an organiser's OK for absentees.
