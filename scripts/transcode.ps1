# Browser-playable 960px MP4s for the UI + one reference frame per camera for zone drawing
New-Item -ItemType Directory -Force C:\argus\data\meva\web, C:\argus\data\meva\frames | Out-Null
Get-ChildItem C:\argus\data\meva\video\*.avi | ForEach-Object {
  ffmpeg -y -loglevel error -ss 5 -i $_.FullName -frames:v 1 "C:\argus\data\meva\frames\$($_.BaseName).jpg"
  ffmpeg -y -loglevel error -i $_.FullName -vf "scale=960:-2" -c:v libx264 -preset veryfast -crf 26 -an -movflags +faststart "C:\argus\data\meva\web\$($_.BaseName).mp4"
  Write-Host "done $($_.BaseName)"
}
