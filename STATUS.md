# STATUS: demo laptop (Jack), auto-updated

_Updated Sat 26 Sep 02:14 IST. Refreshed every 5 min and pushed only when something changed. Details in HANDOFF.md._

## Now (automatic)

Latest work on main:

- Sat 02:09 · officialtanushdeepak-bit · run_demo.ps1 -Camera <index|url> starts the live tile on a real camera with the stage bag rule (-LiveWeights to run anoth…
- Sat 02:08 · jacklachan · Console: Investigate mode in Ask ARGUS. The investigator's steps stream in as it works (what it checked, the footage strips it looked a…
- Sat 02:02 · jacklachan · ARGUS investigator: a tool-using agent that works a case like an analyst (argus/agent.py). Gemini function calling over read-only tools…
- Sat 01:54 · jacklachan · Live incident on stage: the unattended-bag rule on the webcam (live.py --rules). A bag's owner is whoever brought it; it is abandoned w…

In progress on the demo laptop (uncommitted): `backend/argus/agent.py`, `scripts/run_demo.ps1`, `backend/argus/eval/agent_eval.py`, `backend/argus/vision/onepass.py`, `docs/AGENT_VIDEO_SCRIPT.md`

## Demo laptop

- Backend + console: **up** at http://localhost:8000 · 1242 events · briefs by `gemini-flash-latest`
- Live tile: **down**
- AI briefs cached: 9
- Metrics: 4/5 caught · 1242 → 20 → 3

**Upload jobs (Analyse a video):**

- `cdd2679896` 2018-03-15.14-50-00.14-55-00.school.G421.avi (300.07 s): done, 9 events, 0 incidents
- `6b04d15f2a` 2018-03-15.15-15-00.15-20-00.bus.G331.avi (300.3 s): done, 9 events, 1 incident
