# Start the ARGUS demo on the Windows laptop: one backend process that also serves the console.
#
#   powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1            # start (after setup + prepare)
#   powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1 -Prepare   # rebuild pipeline outputs first
#   powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1 -Live      # also start the live inference tile (recorded cafe clip)
#   powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1 -Camera 0  # live tile on webcam 0 with the stage bag rule (implies -Live)
#   ... -Camera 0 -LiveWeights models\weapons_yolo11s.pt                     # live tile with another model (no bag rule: it needs people and bags)
#
# -Camera takes a webcam index (0, 1) or a stream URL such as DroidCam's http://<phone-ip>:4747/video.
#
# -Prepare runs: tracking + valuables pass (skip clips already done) -> rules -> browser MP4s -> evaluation -> brief cache -> console build
param(
    [switch]$Prepare,
    [switch]$Live,
    [string]$Camera = "",
    [string]$LiveWeights = "",
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
    & $Py backend\argus\vision\door_sensor.py
    if ($LASTEXITCODE -ne 0) { Write-Host "door sensor failed" -ForegroundColor Red; exit 1 }

    Step "Threat passes: pose, weapons, violence video model (skips clips already done)"
    & $Py backend\argus\vision\run_threats.py
    if ($LASTEXITCODE -ne 0) { Write-Host "threat passes failed (rules still run without them)" -ForegroundColor Yellow }

    Step "Rules: tracks -> data\events\cctv.jsonl"
    & $Py backend\argus\vision\rules.py
    if ($LASTEXITCODE -ne 0) { Write-Host "rules failed" -ForegroundColor Red; exit 1 }

    Step "Evidence thumbnails: one still per camera event -> data\meva\web\thumbs"
    & $Py backend\argus\vision\thumbs.py
    if ($LASTEXITCODE -ne 0) { Write-Host "thumbnails failed (the console still works without them)" -ForegroundColor Yellow }

    Step "Browser MP4s for the camera wall (only missing ones)"
    New-Item -ItemType Directory -Force data\meva\web | Out-Null
    Get-ChildItem data\meva\video\*.avi | ForEach-Object {
        $out = Join-Path "data\meva\web" ($_.BaseName + ".mp4")
        if (-not (Test-Path $out)) {
            ffmpeg -y -loglevel error -i $_.FullName -vf "scale=960:-2" -c:v libx264 -preset veryfast -crf 26 -g 30 -keyint_min 30 -sc_threshold 0 -an -movflags +faststart $out
            Write-Host "  $out"
        }
        $fast = Join-Path "data\meva\web\fast" ($_.BaseName + ".mp4")   # 5 fps proxy for replay >= 4x
        if (-not (Test-Path $fast)) {
            New-Item -ItemType Directory -Force data\meva\web\fast | Out-Null
            ffmpeg -y -loglevel error -i $_.FullName -vf "fps=5,scale=960:-2" -c:v libx264 -preset veryfast -crf 26 -g 5 -keyint_min 5 -sc_threshold 0 -an -movflags +faststart $fast
            Write-Host "  $fast"
        }
    }

    Step "Evaluation against MEVA ground truth"
    Push-Location backend
    & $Py -m argus.eval.evaluate
    Step "Caching AI briefs (needs internet + GEMINI_API_KEY or ANTHROPIC_API_KEY in .env)"
    & $Py -m argus.brief.warm
    Pop-Location

    Step "Console build"
    npm --prefix frontend install --no-audit --no-fund
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

if ($Camera -ne "") { $Live = $true }
if ($Live) {
    $LiveArgs = @("backend\argus\vision\live.py")
    if ($Camera -ne "") { $LiveArgs += @("--source", $Camera) }
    if ($LiveWeights -ne "") {
        $LiveArgs += @("--weights", $LiveWeights)
        Write-Host "Live tile model: $LiveWeights (the stage bag rule is off: it needs the people-and-bags detector)" -ForegroundColor Yellow
    } elseif ($Camera -ne "") {
        $LiveArgs += @("--rules", "--threats")
        Write-Host "Stage camera rules on: a bag left alone for 15 s, a knife or scissors in hand, a fight (pose + VideoMAE)" -ForegroundColor Yellow
    }
    Step "Starting live inference tile on http://localhost:8001/live.mjpg ($($LiveArgs -join ' '))"
    Start-Process -FilePath $Py -ArgumentList $LiveArgs -WorkingDirectory $Root -WindowStyle Minimized
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
Write-Host "Project website: http://localhost:8000/site/" -ForegroundColor Cyan
Write-Host "`nARGUS is running. Stop it with: powershell -ExecutionPolicy Bypass -File scripts\stop_demo.ps1" -ForegroundColor Cyan
