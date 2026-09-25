#!/usr/bin/env bash
# Publishes the website + offline console demo to Vercel from this machine (no GitHub admin rights needed).
# First time: `npx vercel login` (free Hobby account). The project is named argus-lordofpings, so the site lands on
# https://argus-lordofpings.vercel.app when that name is free (Vercel prints the real URL either way).
#
#   scripts/deploy_site.sh                                     # uses the default domain below
#   RAAH_DOMAIN=my-name.vercel.app scripts/deploy_site.sh      # if Vercel gave the project another domain
#
# Raah only counts visits from the domain its project is set to: keep RAAH_DOMAIN and the Raah project's domain equal.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export RAAH_DOMAIN="${RAAH_DOMAIN:-argus-lordofpings.vercel.app}"
"$ROOT/scripts/build_site.sh"
cd "$ROOT/.deploy/argus-lordofpings"
npx --yes vercel@latest deploy --prod --yes
