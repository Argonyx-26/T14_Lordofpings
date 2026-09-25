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

Next for the frontend owner: box overlays from `/api/tracks/<clip>` on the camera tiles, click-to-jump from
evidence rows to the camera moment, polish (this is the Best UI/UX prize surface).
