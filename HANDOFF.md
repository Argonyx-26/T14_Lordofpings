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

## 11. Fri 25 Sep night: held-out run, evidence stills, Ask ARGUS, and one experiment that failed

**Held-out run (your §12.3): running on the GPU now (`--set all`, A then B).**
- I ran `--set all` instead of `--set A` then `--set B`. `write_report()` only writes the sets from the current run, so a separate B run would have overwritten A's numbers in `docs/HOLDOUT_RESULTS.md`.
- **Two fixes to set A before trusting it** (both in `holdout.py`, commit 0124cff):
  1. **G331 and G336 were re-aimed between 5 and 15 March.** On 5 March the bus-station door zones and door-leaf boxes land on the ceiling (side-by-side check in the table below). Those two cameras now run with **no zones in set A, exactly like an uploaded clip**. No zones were drawn for the new views, so nothing was tuned. G419 and G420 are identical; G421 has shifted a little.
  2. **2 of the 10 annotation files failed to download**, including `2018-03-05.13-15-01.13-20-01.bus.G331`, **the clip with the staged theft**. Without it set A would have said "none staged". I copied both from the MEVA GitLab repo; the other 8 are byte-identical apart from line endings.
- When B finishes I re-score both sets with `--no-detect --set all` (so the zone fix applies), then commit `docs/HOLDOUT_RESULTS.md`.

| Camera | 15 Mar (tuned) vs 5 Mar (held-out) |
|---|---|
| G419, G420 | same view |
| G421 | same room, small shift; zones still land on the doors |
| G331 bus station | **re-aimed**: 15 Mar zones land on the ceiling → run without zones |
| G336 school exterior | **re-aimed** (closer, onto the roundabout) → run without zones |

**Evidence stills (commit 0124cff).** `backend/argus/vision/thumbs.py` renders one still per camera event: a crop around the object with its box, plus the carrier outlined for "changed hands". Output goes to `data/meva/web/thumbs/`, served at `/media/thumbs/<event_id>.jpg`. `run_demo.ps1 -Prepare` builds them after the rules (35 s for 114 stills). In `IncidentDetail` there is a key frame for the strongest camera signal above the evidence list and a small still on each camera event; both replay the moment on click and hide themselves if a still is missing (mock mode, uploads).

**Ask ARGUS (commit aabfae6).** A question box above the incident queue, with `POST /api/ask` and `backend/argus/ask.py`.
- Gemini sees only the surfaced incidents and non-routine signals **up to the replay clock**: never the future, never ground truth. It must cite ids, and citations that aren't in the log are dropped.
- The console shows the cited incidents (click to select) and signals (click to replay).
- Offline, it falls back to an automatic summary of what is open.
- Answers are cached in `data/cache/ask.json`, so **ask the rehearsed questions once on Wi-Fi** and they work offline on stage.
- Verified in the console at 15:19. Asked "Did anyone steal a phone at the plaza?", it answers that the log shows no phone theft there and cites the actual plaza signals.
- `tests/test_ask.py` covers the fallback and the dropping of invented citations. **38 backend tests pass.**
- I restarted the demo backend (only uvicorn, same command as `run_demo.ps1`), so it now has your story titles too.

**Experiment that failed, and a good Q&A answer: an AI second opinion on camera alerts.** `backend/argus/vision/vlm_check.py` (not in the pipeline) shows Gemini three frames around each camera bag alert and asks whether they support the rule. On the 7 alerts in the tuning window:
- It **removed the 1 false alert** (the G638 "bag" is a bush).
- But it **would also have removed 4 of the 6 real ones**: it read moving bags as empty floor and a seated stranger as the owner.
- So it stays out. On stage: *"We tried an AI second opinion on our camera alerts. It threw away real thefts, so the decisions stay with measured rules and the AI only explains."* n = 7; I did not tune the prompt on these 7.

**Bengaluru hook (checked).** On 4 June 2025, a crowd crush outside Chinnaswamy Stadium during RCB's IPL victory celebration killed 11 people and injured more than 50 (suffocation). The Justice D'Cunha commission named unregulated entry at the gates as the root cause. Use it only for the crowding and gate signals, and don't claim ARGUS would have prevented it. Sources: [Deccan Herald](https://www.deccanherald.com/india/karnataka/chinnaswamy-stadium-stampede-karnataka-cabinet-accepts-justice-dcunhas-report-3646246), [LawChakra](https://lawchakra.in/legal-updates/report-on-bengaluru-stampede-stadium/).

**Still to come tonight:** held-out numbers (about 20:45), then a GPU throughput benchmark with the GPU otherwise idle, for a cost-per-camera figure.

**Update 19:55.**
- **Set A scored: the staged theft was missed, with 0 false incidents** (re-scored with the zone fix; same result as before).
  - Why: the stolen suitcase sits at the very bottom edge of the bus-station frame with only its handle in view. YOLO first sees it when the thief lifts it, so the rule never saw it resting and never gave it an owner. The thief then walks out of the bottom of the frame.
  - The only camera signal was "running" at 13:18:32 (score 24; watch is 35), and 5 March has no GPS to corroborate it.
  - Same class of miss as the black purse: an object the detector can't see at rest. **Nothing was tuned on held-out data.**
  - On stage: *"On footage from a different day, we missed the one staged theft (a bag hidden at the edge of the frame) and raised no false alarms."*
- **Set C added** (commit 19cebd3): 12 Mar 10:00–10:15, all six cameras with GPS, nothing staged.
  - I checked side by side that all six views match 15 March, so the tuned zones apply. This makes it a clean second false-alarm test on another day.
  - `--set` now takes several sets (`--no-detect --set A B C`), and the report **merges** earlier runs instead of overwriting them.
- **Timing:** the venue network dropped to under 1 MB/s, so set B is still downloading. Expected order: B on the GPU until about 21:25 (C downloads meanwhile), then the GPU benchmark (live tile stopped for 2 minutes), then C on the GPU overnight. I'll push `docs/HOLDOUT_RESULTS.md` after B and again after C.
- **Ask ARGUS offline:** on Wi-Fi, run `cd backend; ..\.venv\Scripts\python -m argus.ask "2018-03-15 15:19:00" "What happened at the bus station after 15:10?"` for each question you'll ask on stage, **at the replay time you'll pause at**. On stage the answer then comes from the cache in under a second, with no network. Verified: the command-line answer and the console answer at 15:19 hit the same cache entry.

**Door sensor, 20:20 (Mohit asked for accuracy work; measured on the tuning window only; nothing changed in the rules).** `python -m argus.vision.door_eval` scores the door rule per camera and accepts overrides, e.g. `G331=leaf`.
- **G331 bus, P 0.02:** the doors stand open. MEVA labels **1** `opens_facility_door` in 20 min, while dozens of people walk through (checked on frames). Our 63 "false" detections are mostly real passages, and MEVA has no passage labels in these clips. The leaf method there is worse (93 detected, 0 correct). **Report G331 as "doors held open: we count passages, the annotation counts openings".**
- **G336, recall 0:** all 10 annotated openings are at one door about 100 m away (located from MEVA's box annotations). YOLO at 960 px detects nobody there (0 of 10). That's out of range for this camera, and no zone fixes it.
- **G421 extra left-door triggers:** I tested "someone nearer the camera covers the door top". The overlap was 0 at every one of those events, so the hypothesis is wrong and I reverted it.
- **G638:** no timing bias (median offset −1.1 s), so nothing to calibrate.
- Conclusion: the honest door number is still **indoor P 0.54 / R 0.75**. Sets B and C will test it on unseen footage.

## 12. Fri 25 Sep late: mentor round. High-security profiles, weapons, violence, dealing, and numbers with n

The mentors asked for suspicious-activity detection (fights, stabbing, knives), more training data, "numbers to back it up", and a high-security (airport) setting that can be relaxed for a campus. Everything below is pushed; tests: **42 backend + 14 frontend pass**.

### What was added
- **Security profiles** (`backend/argus/config/profiles.yaml`, top-bar switch **Airport | School / college | Public park**, `POST /api/profile` re-scores the replay so far). The vision rules always run at their most sensitive; a profile sets the open/watch thresholds, an area-criticality floor, per-signal weights and minimum evidence, and which signals go straight to a human. **Default: Airport.** Campus = exactly the tuned site.
- **New detectors** (`backend/argus/vision/threats.py`, hooked into `ClipRules.run`; run on uploads too):

  | Signal | How | Title |
  |---|---|---|
  | `weapon_visible` | YOLO11s fine-tuned on real CCTV weapons (`train_weapons.py`); a weapon on a person on 3 of 6 frames | Weapon seen |
  | `violence` | pose features from YOLO11s-pose → random-forest classifier (`violence.py`) on 2.5 s windows, 2 in a row ≥ 0.7 | Fight or violent struggle |
  | `person_down` | body lying (box wider than tall, torso tilted ≥ 60°) for ≥ 3 s | Person on the ground |
  | `hand_off` | two people's wrists meet for ≥ 0.4 s | Hand-to-hand exchange |
  | `dealing_pattern` | ≥ 3 hand-offs with ≥ 2 different people in 10 min by someone who stays put | Repeated hand-offs (possible dealing) |

  Stories: weapon + violence = **"Armed assault in progress"** (armed response); violence + person down = **"Assault: person on the ground"**. Weapons and violence open an incident on their own in every profile.
- **New weights (not in git, on the demo laptop in `models/`):** `yolo11s-pose.pt` (Ultralytics release), `weapons_yolo11s.pt` (fine-tuned here), `violence.joblib`.

### Numbers (all on data never used to tune or train, except the first row)
| What | Result | n / method |
|---|---|---|
| Theft & abandonment (tuning window) | 4/5, 0 false | MEVA 15 Mar; every staged theft/abandonment MEVA publishes here |
| Profiles on that footage | Airport 4/5 + 6 on watch · Campus 4/5 · Park 2/5; **0 false incidents in all three** | same 30 min |
| **Fights** | **accuracy 74.7 %, ROC-AUC 0.82**; at the pipeline's 0.7: 80/150 fights, 17/150 false (precision 0.83) | 300 real CCTV clips (Akti et al. 2019, MIT), 5-fold CV **grouped by source recording** (74 recordings). The dataset's authors reported **72 %** with Xception/Bi-LSTM/attention on a random 80/20 split (their Table IV). Random forest chosen over 2 alternatives on the same CV (small optimistic bias). |
| **Weapons** | AP50 **handgun 0.51, rifle 0.54**, knife 0.09; **42/84 weapon appearances alerted; 14 false alerts in 29 min** (people holding dark phones) | 3,511 frames from a CCTV camera **never trained on** (Univ. of Seville mock armed attack, CC BY-NC 4.0; trained on the other 2 cameras, fixed 30 epochs, no validation on the test camera). A phone veto was tried and rejected (14 → 11 false, 6 real lost). |
| Doors & hand-offs at scale | *running* (20 unseen MEVA clips, 100 camera-minutes; full set = 306 clips / 1,337 door openings / 176 hand-offs on a GPU server) | `python -m argus.eval.scale` |

### How to say it on stage
- "Airport mode by default; a school or a park turns it down, and we measured what that costs on the same footage."
- Fights: "Trained on 300 real CCTV fight clips, tested so that no recording is ever both trained and tested on: **75 % accuracy, better than the dataset authors' own 72 %**, from body pose alone, on a laptop GPU."
- Weapons: "Handguns and rifles are found in half of their appearances on a camera the model never saw. Gun detection on CCTV is an open research problem, which is why a weapon alert always goes to a human with a still, and only becomes 'armed assault' when a second signal agrees." **Don't claim knives.**
- Dealing: "Cameras can't see drugs. We flag the *pattern*: repeated hand-offs with different people by someone who stays put, for a human to judge."
- Demo: MEVA has no fights or weapons. For a live proof, film 2–3 short, obviously staged clips at the venue (a pretend scuffle, someone holding a toy or kitchen knife, a hand-off) and use **Analyse a video**.
