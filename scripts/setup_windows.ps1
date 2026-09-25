# One-time setup of the ARGUS demo laptop (Windows 10/11). Safe to re-run: finished steps are skipped.
#   powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$Py = Join-Path $Root ".venv\Scripts\python.exe"

function Step($msg) { Write-Host "`n== $msg" -ForegroundColor Cyan }
function Fail($msg) { Write-Host "FAILED: $msg" -ForegroundColor Red; exit 1 }
function Ok($msg)   { Write-Host "OK  $msg" -ForegroundColor Green }

Step "1/7 Tools"
$missing = @()
if (-not (Get-Command py -ErrorAction SilentlyContinue))         { $missing += "Python 3.12:  winget install -e --id Python.Python.3.12" }
if (-not (Get-Command node -ErrorAction SilentlyContinue))       { $missing += "Node.js LTS:  winget install -e --id OpenJS.NodeJS.LTS" }
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue))     { $missing += "FFmpeg:       winget install -e --id Gyan.FFmpeg" }
if (-not (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) { $missing += "NVIDIA driver 580 or newer" }
if ($missing.Count -gt 0) {
    $missing | ForEach-Object { Write-Host "MISSING  $_" -ForegroundColor Red }
    Fail "install the tools above, close and reopen PowerShell, then run this script again"
}
nvidia-smi --query-gpu=name,driver_version --format=csv,noheader
Ok "python, node, ffmpeg, nvidia driver"

Step "2/7 Python environment (.venv)"
if (-not (Test-Path $Py)) { py -3.12 -m venv .venv; if ($LASTEXITCODE -ne 0) { Fail "could not create .venv" } }
& $Py -m ensurepip --upgrade 2>$null | Out-Null   # a .venv made by uv has no pip
& $Py -m pip install --upgrade pip --quiet
$cuda = (& $Py -c "import torch; print(torch.cuda.is_available())" 2>&1 | Select-Object -Last 1)
if ("$cuda" -ne "True") {
    Write-Host "Installing PyTorch with CUDA 13 (needed for the RTX 50-series)..."
    & $Py -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130 --no-cache-dir
    if ($LASTEXITCODE -ne 0) { Fail "PyTorch install" }
}
& $Py -m pip install --quiet -r backend\requirements.txt ultralytics opencv-python
if ($LASTEXITCODE -ne 0) { Fail "pip install of backend requirements" }
& $Py -c "import torch; assert torch.cuda.is_available(), 'CUDA not available'; print('GPU', torch.cuda.get_device_name(0), torch.cuda.get_arch_list()); print(torch.randn(2, device='cuda') * 2)"
if ($LASTEXITCODE -ne 0) { Fail "GPU check. If it mentions sm_120 / no kernel image: pip uninstall -y torch torchvision, then re-run this script" }
Ok "Python + CUDA"

Step "3/7 Model weights (models\)"
New-Item -ItemType Directory -Force models | Out-Null
Push-Location models
& $Py -c "from ultralytics import YOLO; YOLO('yolo11s.pt'); YOLO('yolo11m.pt')"
Pop-Location
if ((Test-Path models\yolo11s.pt) -and (Test-Path models\yolo11m.pt)) { Ok "models\yolo11s.pt, models\yolo11m.pt" } else { Fail "could not download yolo11s.pt" }

Step "4/7 MEVA data (data\meva)"
$v = @(Get-ChildItem data\meva\video\*.avi -ErrorAction SilentlyContinue).Count
$a = @(Get-ChildItem data\meva\ann\*.yml -ErrorAction SilentlyContinue).Count
$g = @(Get-ChildItem data\meva\gps\*.gpx -ErrorAction SilentlyContinue).Count
if ($v -lt 10 -or $a -lt 9 -or $g -lt 6) {
    Write-Host "videos $v/10, annotations $a/9, gps $g/6 -> fetching what is missing"
    powershell -ExecutionPolicy Bypass -File scripts\get_meva.ps1
    if ($LASTEXITCODE -ne 0) { Fail "data download" }
}
Ok "videos, annotations, GPS present"

Step "5/7 Console (frontend)"
npm --prefix frontend install --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { Fail "npm install" }
npm --prefix frontend run build
if ($LASTEXITCODE -ne 0) { Fail "frontend build" }
Ok "frontend\dist built"

Step "6/7 Secrets (.env)"
if (-not (Test-Path .env)) {
    "ANTHROPIC_API_KEY=" | Out-File -Encoding ascii .env
    Write-Host "Created .env - put your key after ANTHROPIC_API_KEY= (briefs fall back to a template without it)" -ForegroundColor Yellow
} else { Ok ".env exists" }

Step "7/7 Tests"
Push-Location backend
& $Py -m pytest -q
$testsOk = ($LASTEXITCODE -eq 0)
Pop-Location
if (-not $testsOk) { Fail "backend tests" }
Ok "backend tests"

Write-Host "`nSetup complete. Next:  powershell -ExecutionPolicy Bypass -File scripts\run_demo.ps1 -Prepare" -ForegroundColor Cyan
