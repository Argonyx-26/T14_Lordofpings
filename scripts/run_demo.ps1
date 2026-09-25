# Start the ARGUS demo on the Windows laptop: one backend process that also serves the console.
#
#   powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1            # start (after setup + prepare)
#   powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1 -Prepare   # rebuild pipeline outputs first
#   powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1 -Live      # also start the live inference tile
#
# -Prepare runs: tracking + valuables pass (skip clips already done) -> rules -> browser MP4s -> evaluation -> brief cache -> console build
param(
    [switch]$Prepare,
    [switch]$Live,
    [switch]$NoBrowser
)
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { Write-Host "Run scripts\setup_windows.ps1 first." -ForegroundColor Red; exit 1 }

function Step($msg) { Write-Host "`n== $msg" -ForegroundColor Cyan }

if ($Prepare) {
    Step "Tracking (YOLO + ByteTrack; clips already tracked are skipped)"
    & $Py -m backend.argus.vision.run_tracks
    if ($LASTEXITCODE -ne 0) { Write-Host "tracking failed" -ForegroundColor Red; exit 1 }

    Step "Valuables pass (bags, laptops, phones at 1280 px; skips clips already done)"
    & $Py -m backend.argus.vision.run_bags
    if ($LASTEXITCODE -ne 0) { Write-Host "valuables pass failed" -ForegroundColor Red; exit 1 }

    Step "Door sensor (door-leaf motion per camera; skips clips already done)"
    & $Py backendrgusision\door_sensor.py
    if ($LASTEXITCODE -ne 0) { Write-Host "door sensor failed" -ForegroundColor Red; exit 1 }

    Step "Rules: tracks -> data\events\cctv.jsonl"
    & $Py backend\argus\vision\rules.py
    if ($LASTEXITCODE -ne 0) { Write-Host "rules failed" -ForegroundColor Red; exit 1 }

    Step "Browser MP4s for the camera wall (only missing ones)"
    New-Item -ItemType Directory -Force data\meva\web | Out-Null
    Get-ChildItem data\meva\video\*.avi | ForEach-Object {
        $out = Join-Path "data\meva\web" ($_.BaseName + ".mp4")
        if (-not (Test-Path $out)) {
            ffmpeg -y -loglevel error -i $_.FullName -vf "scale=960:-2" -c:v libx264 -preset veryfast -crf 26 -an -movflags +faststart $out
            Write-Host "  $out"
        }
    }

    Step "Evaluation against MEVA ground truth"
    Push-Location backend
    & $Py -m argus.eval.evaluate
    Step "Caching AI briefs (needs internet + ANTHROPIC_API_KEY in .env)"
    & $Py -m argus.brief.warm
    Pop-Location

    Step "Console build"
    npm --prefix frontend run build
}

if (-not (Test-Path frontend\dist\index.html)) {
    Step "Console build (first run)"
    npm --prefix frontend install --no-audit --no-fund
    npm --prefix frontend run build
}

Step "Stopping anything already on ports 8000 / 8001"
foreach ($port in 8000, 8001) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
}

Step "Starting backend + console on http://localhost:8000"
Start-Process -FilePath $Py -ArgumentList "-m uvicorn argus.api.main:app --host 127.0.0.1 --port 8000" `
    -WorkingDirectory (Join-Path $Root "backend") -WindowStyle Minimized

if ($Live) {
    Step "Starting live inference tile on http://localhost:8001/live.mjpg"
    Start-Process -FilePath $Py -ArgumentList "backend\argus\vision\live.py" -WorkingDirectory $Root -WindowStyle Minimized
}

$health = $null
for ($i = 0; $i -lt 60 -and -not $health; $i++) {
    try { $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 2 } catch { Start-Sleep -Seconds 1 }
}
if (-not $health) { Write-Host "Backend did not come up - open its minimized window to see the error." -ForegroundColor Red; exit 1 }
Write-Host ("Events loaded: " + $health.events + "  by source: " + ($health.by_source | ConvertTo-Json -Compress)) -ForegroundColor Green
if (-not $health.by_source.cctv) {
    Write-Host "No CCTV events loaded - run with -Prepare (or python backend\argus\vision\rules.py)." -ForegroundColor Yellow
}

if (-not $NoBrowser) { Start-Process "http://localhost:8000" }
Write-Host "`nARGUS is running. Stop it with: powershell -ExecutionPolicy Bypass -File scripts\stop_demo.ps1" -ForegroundColor Cyan
