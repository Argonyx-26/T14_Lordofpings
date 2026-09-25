# Stop the ARGUS demo processes (backend on 8000, live tile on 8001, vite dev server on 5173).
#   powershell -ExecutionPolicy Bypass -File scripts\stop_demo.ps1
foreach ($port in 8000, 8001, 5173) {
    Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-Host "stopped process on port $port"
    }
}
