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

1. **IN PROGRESS (Mohit): the camera wall stutters at 2× / 5× / 10× replay.** This is not the live tile (verified: 29.7 fps produced and 29.7 fps received by a client).
   - Cause, from reading `CameraWall.tsx` `Tile`: whenever drift from the replay clock exceeds 1.5 s the video seeks, and `playbackRate` is capped at 16.
   - The MP4s (`data/meva/web`, from `run_demo.ps1` / `transcode.ps1`) use the x264 default GOP (~8 s), so every seek decodes up to 8 s of frames. At high speed the fixed 1.5 s threshold is crossed constantly, which gives seek stutter.
   - **At 20× (the speed in the PITCH run-sheet) the video can never keep up.**
   - Planned fix: speed-scaled drift tolerance and rate nudging in `Tile`, plus MP4s re-encoded with a 1 s GOP. Mohit is doing this next and will update this section.
2. `run_demo.ps1 -Prepare`: "Console build" (`npm run build`) runs **before** `npm install`, so on a fresh machine it fails first. The later first-run branch recovers, but `npm install` should come before the build.
3. PITCH run-sheet says **20×**. Until issue 1 is fixed, demo at **10×** or lower.

## 6. Before going on stage (demo laptop)

- Charger in, Windows power mode **Best performance**, **Energy Saver off**, sleep **Never**. Close Roblox, Steam, and the Discord overlay.
- `.env` in the repo root holds `GEMINI_API_KEY` (gitignored; never commit it). The briefs are already cached, so no internet is needed on stage.
- Once: Wi-Fi off, then `scripts\run_demo.ps1 -Live`, to prove the demo works offline. Stop it with `scripts\stop_demo.ps1`.
- Console at http://localhost:8000, live tile at http://localhost:8001/live.mjpg.

## 7. Ground rules (unchanged)

- Theft and abandonment annotations are **eval only**. Nothing under `backend/argus/vision/` reads them; only `eval/evaluate.py` does.
- No video, weights, keys or `data/` in git. Only the `.pt` weights came from Skylinev2; no code did.
- Shared backend code stays cross-platform (Tanush is on a Mac). Windows-only calls live only in vision scripts, guarded by `sys.platform` (e.g. `live.py`'s `no_power_throttling()`).
