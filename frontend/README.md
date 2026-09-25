# ARGUS console (React + Vite + Tailwind v4)

```bash
npm install
npm run dev            # http://localhost:5173 — talks to the backend at http://localhost:8000
```

- **Live mode** (default): connects to `ws://localhost:8000/ws`, replay controls call `POST /api/replay`.
- **Mock mode**: open `http://localhost:5173/?mock=1`. Uses `src/mock/*.json`: the real door + GPS window
  plus two *hypothetical* CCTV events (flagged `fixture: true`) so the UI has open incidents to design against.
  A "MOCK DATA" badge is always shown. Never demo in mock mode.
- Point at another backend with `VITE_ARGUS_API=http://<host>:8000 npm run dev`.
- Camera tiles play `data/meva/web/<clip>.mp4` (served by the backend at `/media`) in sync with the replay clock.

Types in `src/types.ts` mirror `backend/argus/schema.py`.

Also in the console: detection boxes over each camera tile (from `/api/tracks/<clip>`), click an evidence row
to replay that moment on the enlarged camera, the live inference view (`scripts\run_demo.ps1 -Live`), and
**Analyse a video** (upload any clip; `UploadView.tsx`, backend `argus/uploads.py`). `?incident=INC-0007`
preselects an incident.
