# ARGUS console (React + Vite + Tailwind v4)

```bash
npm install
npm run dev            # http://localhost:5173 — talks to the backend at http://localhost:8000
```

- **Live mode** (default): connects to `ws://localhost:8000/ws`, replay controls call `POST /api/replay`.
- **Offline demo** (`?mock`, or a build with `VITE_ARGUS_MOCK=1`: the hosted console on Vercel): no backend. Loads
  `src/mock/config.json` and `src/mock/snapshot.json`, a snapshot of the replay made by
  `python -m argus.export_snapshot` on the demo laptop (incidents, evidence, forecasts, intel). The top bar says
  *Offline demo · real snapshot*, or how many placeholder events it holds (`attrs.fixture`), and those evidence rows
  say *placeholder, not a detection*. Anything that needs the backend (replay, uploads, decisions, the supervisor
  desk) says so.
- Point at another backend with `VITE_ARGUS_API=http://<host>:8000 npm run dev`.
- Camera tiles play `data/meva/web/<clip>.mp4` (served by the backend at `/media`) in sync with the replay clock.

Types in `src/types.ts` mirror `backend/argus/schema.py`.

Also in the console: detection boxes over each camera tile (from `/api/tracks/<clip>`), click an evidence row
to replay that moment on the enlarged camera, the live inference view (`scripts\run_demo.ps1 -Live`), and
**Analyse a video** (upload any clip; `UploadView.tsx`, backend `argus/uploads.py`). `?incident=INC-0007`
preselects an incident; `?plan=1` opens the response planner, `?report=1` the case report, `?upload=<id>` an
analysed clip, `?noboot` skips the boot sequence.

Roles: every request carries `X-Argus-Role` (and `X-Argus-Pin` when the backend sets a supervisor PIN), see
`lib.ts` `setSession()`; what each role may see is decided by the backend (`backend/argus/access.py`).
