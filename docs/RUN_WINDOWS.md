# Running the ARGUS demo on the Windows laptop

The live demo runs on the Windows laptop with the RTX 5060. Everything below is PowerShell, run from the repo
root (e.g. `C:\argus`). The scripts work from any clone path.

## 1. One-time setup (≈10 min, needs internet)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
```

It checks the tools (Python 3.12, Node, FFmpeg, NVIDIA driver ≥ 580), creates `.venv`, installs PyTorch with
CUDA 13 (required for the RTX 50-series) only if CUDA isn't already working, installs the backend and vision
requirements, downloads `models\yolo11s.pt`, fetches any missing MEVA data, builds the console, creates `.env`,
and runs the backend tests. It stops at the first problem and says how to fix it. Re-running is safe.

Then put the Claude API key in `.env` (repo root):

```
ANTHROPIC_API_KEY=sk-ant-...
```

## 2. Prepare the demo data (after any change to vision rules, zones or thresholds)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1 -Prepare
```

Runs, in order: tracking (clips already tracked are skipped) → rules → `data\events\cctv.jsonl` → browser MP4s
for the camera wall (missing ones only) → evaluation against MEVA ground truth → caching of AI briefs (needs
internet and the key) → console build. Then it starts the demo.

## 3. Start the demo (on stage: no internet needed after step 2)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1          # console at http://localhost:8000
powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1 -Live    # + live inference tile on :8001
```

One backend process serves the API, the videos and the console, so the whole demo is one URL:
**http://localhost:8000**. The script frees ports 8000/8001 first, waits until the backend is healthy, prints
how many events it loaded per stream (warns if CCTV events are missing), and opens the browser.

Stop everything:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\stop_demo.ps1
```

## Before going on stage

- Laptop on charger, Windows power mode **Best performance**, sleep **Never**.
- NVIDIA Control Panel → Manage 3D settings → Program settings → `.venv\Scripts\python.exe` →
  **High-performance NVIDIA processor**.
- Run step 2 once with internet so every brief is cached, then **turn Wi-Fi off and run step 3** to prove the
  demo works offline. Briefs fall back to the template if anything is missing, never to an error.
- In the console: **Reset**, pick the speed (10–20×), use **Jump to…** for the staged scenarios.

## If something goes wrong

| Symptom | Fix |
|---|---|
| `no kernel image is available` / `sm_120 is not compatible` | `.venv\Scripts\python -m pip uninstall -y torch torchvision`, then re-run setup (reinstalls the cu130 build) |
| Script blocked by execution policy | Always start scripts with `powershell -ExecutionPolicy Bypass -File ...` |
| Browser shows "offline" badge | Backend window crashed: run `scripts\run_demo.ps1` again; its minimized window shows the error |
| Camera tiles say "Footage not loaded" | `data\meva\web\*.mp4` missing: run with `-Prepare` (or install FFmpeg) |
| Metrics strip has no "Staged incidents caught" | Run `-Prepare` (it writes `data\cache\metrics.json`) |
| Briefs say "template" | No key in `.env` or no internet when `-Prepare` ran: add the key, run `-Prepare` online once |
| Port already in use | `scripts\stop_demo.ps1` |
| Live tile stutters | Stop it (close its window); nothing else depends on it |
