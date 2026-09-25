#!/usr/bin/env bash
# Builds the public website into .deploy/argus-lordofpings/:
#   /            the project site (site/) and the judges' page
#   /console/    the console's offline demo: a real snapshot of the replay, no backend needed
# with Raah analytics in every page when RAAH_DOMAIN is set (the domain the site is published on).
# The demo laptop never uses this: its console and site are served offline by the backend.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/.deploy/argus-lordofpings"
RAAH_PID="${RAAH_PID:-proj_wwwp2pa8sqx7ytp4}"
RAAH_DOMAIN="${RAAH_DOMAIN:-}"

rm -rf "$OUT" && mkdir -p "$OUT"
(
  cd "$ROOT/frontend"
  [ -d node_modules ] || npm ci --no-audit --no-fund
  VITE_ARGUS_MOCK=1 npx vite build --base /console/ --outDir "$OUT/console" --emptyOutDir
)
cp -R "$ROOT/site/." "$OUT/"
rm -f "$OUT/README.md"

if [ -n "$RAAH_DOMAIN" ]; then
  tag="<script defer src=\"https://t.raah.dev/script.js\" data-pid=\"$RAAH_PID\" data-domain=\"$RAAH_DOMAIN\"></script>"
  for f in "$OUT/index.html" "$OUT/judges.html" "$OUT/console/index.html"; do
    TAG="$tag" perl -0pi -e 's#</head>#  $ENV{TAG}\n</head>#' "$f"
  done
  echo "Raah analytics added for $RAAH_DOMAIN"
else
  echo "RAAH_DOMAIN not set: built without analytics"
fi
echo "Built $OUT"
