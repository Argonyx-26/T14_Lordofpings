# Browser-playable 960px MP4s for the UI (30 fps, 1 s keyframes for cheap seeks), a 5 fps proxy used by the
# camera wall at replay speeds >= 4x, and one reference frame per camera for zone drawing
New-Item -ItemType Directory -Force C:\argus\data\meva\web, C:\argus\data\meva\web\fast, C:\argus\data\meva\frames | Out-Null
Get-ChildItem C:\argus\data\meva\video\*.avi | ForEach-Object {
  ffmpeg -y -loglevel error -ss 5 -i $_.FullName -frames:v 1 "C:\argus\data\meva\frames\$($_.BaseName).jpg"
  ffmpeg -y -loglevel error -i $_.FullName -vf "scale=960:-2" -c:v libx264 -preset veryfast -crf 26 -g 30 -keyint_min 30 -sc_threshold 0 -an -movflags +faststart "C:\argus\data\meva\web\$($_.BaseName).mp4"
  ffmpeg -y -loglevel error -i $_.FullName -vf "fps=5,scale=960:-2" -c:v libx264 -preset veryfast -crf 26 -g 5 -keyint_min 5 -sc_threshold 0 -an -movflags +faststart "C:\argus\data\meva\web\fast\$($_.BaseName).mp4"
  Write-Host "done $($_.BaseName)"
}
