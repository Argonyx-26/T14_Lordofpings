#!/usr/bin/env bash
# macOS/Linux: fetch the small MEVA files the backend needs (annotations, GPS, site map). No video.
# Video for the vision pipeline: scripts/get_meva.ps1 (Windows).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)/data/meva"
GL=https://gitlab.kitware.com/meva/meva-data-repo/-/raw/master
A=$GL/annotation/DIVA-phase-2/MEVA
mkdir -p "$ROOT"/{ann,gps,video,web}

while read -r stem aset; do
  curl -fsSL -o "$ROOT/ann/$stem.activities.yml" "$A/$aset/$stem.activities.yml"
  echo "ann  $stem"
done <<'EOF'
2018-03-15.14-50-00.14-55-00.school.G421 kitware/2018-03-15/14
2018-03-15.14-50-00.14-55-00.school.G419 kitware-meva-training/2018-03-15/14
2018-03-15.14-50-01.14-55-01.school.G420 kitware/2018-03-15/14
2018-03-15.14-50-00.14-55-00.school.G638 kitware-meva-training/2018-03-15/14
2018-03-15.14-50-00.14-55-00.school.G336 kitware-meva-training/2018-03-15/14
2018-03-15.14-50-00.14-55-00.bus.G331 kitware-meva-training/2018-03-15/14
2018-03-15.14-55-00.15-00-00.bus.G331 kitware-meva-training/2018-03-15/15
2018-03-15.15-10-00.15-15-00.bus.G331 kitware-meva-training/2018-03-15/15
2018-03-15.15-15-00.15-20-00.bus.G331 kitware-meva-training/2018-03-15/15
EOF

curl -fsSL -o "$ROOT/gps.zip" "$GL/metadata/gps/gps-for-released-meva-data.zip"
TMP=$(mktemp -d); unzip -q -o "$ROOT/gps.zip" -d "$TMP"
for s in 14-50 14-55 15-00 15-05 15-10 15-15; do cp "$(find "$TMP" -name "2018-03-15.$s-00.gpx")" "$ROOT/gps/"; done
rm -rf "$TMP"
curl -fsSL -o "$ROOT/site-map.pdf" https://mevadata-public-01.s3.amazonaws.com/phase2-known-facility-site-map.pdf
curl -fsSL -o "$ROOT/clip-table.txt" "$GL/metadata/meva-clip-camera-and-time-table.txt"
echo "done: $(ls "$ROOT/ann" | wc -l) annotation files, $(ls "$ROOT/gps" | wc -l) GPX files"
