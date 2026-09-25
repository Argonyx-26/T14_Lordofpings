$ErrorActionPreference = "Stop"
$root = Join-Path (Split-Path -Parent $PSScriptRoot) "data\meva"   # repo-relative, works from any clone path
$vid  = "$root\video"; $ann = "$root\ann"; $gps = "$root\gps"
New-Item -ItemType Directory -Force -Path $vid,$ann,$gps | Out-Null
$S3  = "https://mevadata-public-01.s3.amazonaws.com/drops-123-r13/2018-03-15"
$GL  = "https://gitlab.kitware.com/meva/meva-data-repo/-/raw/master"
$A   = "$GL/annotation/DIVA-phase-2/MEVA"

# stem, S3 hour folder, annotation set ('' = no annotation), expected bytes
$clips = @(
 @("2018-03-15.14-50-00.14-55-00.school.G421","14","kitware/2018-03-15/14",142880030),
 @("2018-03-15.14-50-00.14-55-00.school.G419","14","kitware-meva-training/2018-03-15/14",78883804),
 @("2018-03-15.14-50-01.14-55-01.school.G420","14","kitware/2018-03-15/14",66614110),
 @("2018-03-15.14-50-00.14-55-00.school.G638","14","kitware-meva-training/2018-03-15/14",190112066),
 @("2018-03-15.14-50-00.14-55-00.school.G336","14","kitware-meva-training/2018-03-15/14",260260028),
 @("2018-03-15.14-50-00.14-55-00.school.G474","14","",5987886),
 @("2018-03-15.14-50-00.14-55-00.bus.G331","14","kitware-meva-training/2018-03-15/14",112414584),
 @("2018-03-15.14-55-00.15-00-00.bus.G331","15","kitware-meva-training/2018-03-15/15",108866912),
 @("2018-03-15.15-10-00.15-15-00.bus.G331","15","kitware-meva-training/2018-03-15/15",108593042),
 @("2018-03-15.15-15-00.15-20-00.bus.G331","15","kitware-meva-training/2018-03-15/15",103333370)
)

foreach ($c in $clips) {
  $stem,$hh,$aset,$size = $c
  # accept either <stem>.avi or <stem>.r13.avi that you may already have
  $existing = @("$vid\$stem.avi","$vid\$stem.r13.avi") | Where-Object { Test-Path $_ } | Select-Object -First 1
  if ($existing -and (Get-Item $existing).Length -eq $size) {
    if ($existing -ne "$vid\$stem.avi") { Rename-Item $existing "$stem.avi" }
    Write-Host "OK      $stem"
  } else {
    Write-Host "FETCH   $stem"
    curl.exe -fL --retry 3 -C - -o "$vid\$stem.avi" "$S3/$hh/$stem.r13.avi"
    if ((Get-Item "$vid\$stem.avi").Length -ne $size) { throw "Size mismatch: $stem" }
  }
  if ($aset -ne "") { curl.exe -fsL -o "$ann\$stem.activities.yml" "$A/$aset/$stem.activities.yml" }
}

# GPS (small zip). Keep only the 14:50–15:20 slots.
curl.exe -fL -o "$root\gps.zip" "$GL/metadata/gps/gps-for-released-meva-data.zip"
Expand-Archive -Force "$root\gps.zip" "$root\gps_all"
Get-ChildItem "$root\gps_all" -Recurse -Filter "2018-03-15.1*.gpx" |
  Where-Object { $_.Name -match '2018-03-15\.(14-5|15-[01])' } | Copy-Item -Destination $gps

# Site map (named zones and camera placement) and clip timing table
curl.exe -fL -o "$root\site-map.pdf" "https://mevadata-public-01.s3.amazonaws.com/phase2-known-facility-site-map.pdf"
curl.exe -fL -o "$root\clip-table.txt" "$GL/metadata/meva-clip-camera-and-time-table.txt"
Write-Host "DONE. Videos:" (Get-ChildItem $vid).Count " Annotations:" (Get-ChildItem $ann).Count " GPX:" (Get-ChildItem $gps).Count
