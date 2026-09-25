#!/usr/bin/env bash
# Builds the public website into .deploy/argus-lordofpings/:
#   /            the project site (site/) and the judges' page
#   /console/    the console's offline demo: a real snapshot of the replay, no backend needed
# with Raah analytics in every page when RAAH_DOMAIN is set (the domain the site is published on):
#   - the beacon (page views, visits, journeys, referrers, Web Vitals) on the site, the judges' page and the console
#   - named events: clicks on anything marked data-raah-event (open_console, open_judges, open_github) and outbound
#     links, and the console's own events (case_report_open/print/copy, plan_response_open, pattern_link_open,
#     ask_argus: lib.ts track()); no incident content is ever sent
#   - the public live-visitor badge in the site footer (the data-raah-badge slot)
# The demo laptop never uses this: its console and site are served offline by the backend.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/.deploy/argus-lordofpings"
RAAH_PID="${RAAH_PID:-proj_wwwp2pa8sqx7ytp4}"
RAAH_DOMAIN="${RAAH_DOMAIN:-}"

# keep the Vercel project link (.vercel/) across rebuilds, or the next deploy would create a new project
if [ -d "$OUT/.vercel" ]; then mv "$OUT/.vercel" "$ROOT/.deploy/.vercel.keep"; fi
rm -rf "$OUT" && mkdir -p "$OUT"
if [ -d "$ROOT/.deploy/.vercel.keep" ]; then mv "$ROOT/.deploy/.vercel.keep" "$OUT/.vercel"; fi
(
  cd "$ROOT/frontend"
  [ -d node_modules ] || npm ci --no-audit --no-fund
  VITE_ARGUS_MOCK=1 npx vite build --base /console/ --outDir "$OUT/console" --emptyOutDir
)
cp -R "$ROOT/site/." "$OUT/"
rm -f "$OUT/README.md"

if [ -n "$RAAH_DOMAIN" ]; then
  # the queue shim runs before the deferred beacon, so events clicked while it loads are kept (raah drains raah.q)
  shim='<script>window.raah=window.raah||{q:[]};document.addEventListener("click",function(e){var a=e.target&&e.target.closest&&e.target.closest("[data-raah-event],a[href^=\"http\"]");if(!a)return;var n=a.getAttribute("data-raah-event")||"outbound_link",p={page:location.pathname};if(a.href)p.href=String(a.href).slice(0,255);var r=window.raah;try{r.track?r.track(n,p):(r.q=r.q||[]).push(["track",n,p])}catch(_){}},true)</script>'
  tag="<script defer src=\"https://t.raah.dev/script.js\" data-pid=\"$RAAH_PID\" data-domain=\"$RAAH_DOMAIN\"></script>"
  for f in "$OUT/index.html" "$OUT/judges.html" "$OUT/console/index.html"; do
    TAG="$shim$tag" perl -0pi -e 's#</head>#  $ENV{TAG}\n</head>#' "$f"
  done
  badge="<span data-raah-live data-pid=\"$RAAH_PID\" data-domain=\"$RAAH_DOMAIN\" data-theme=\"dark\" data-sticky=\"false\"></span><script async src=\"https://t.raah.dev/badge.js\"></script>"
  BADGE="$badge" perl -0pi -e 's#<span data-raah-badge></span>#$ENV{BADGE}#' "$OUT/index.html"
  echo "Raah analytics added for $RAAH_DOMAIN"
else
  echo "RAAH_DOMAIN not set: built without analytics"
fi
echo "Built $OUT"
