#!/bin/sh
# Push roost to the Sprite and restart it. Run from the repo root.
#   ./scripts/deploy.sh        code, sample documents and the web page
#   ./scripts/deploy.sh api    everything except web/index.html (the live page stays as it is)
# Then ./scripts/smoke.sh for one live pass that cleans up after itself.
set -eu
cd "$(dirname "$0")/.."
files="service.py auth.py accounts.py userspace.py digest.py mail.py store.py extract.py due.py \
       gateway.py box.py nest.py ingest.py decide.py ask.py scripts/smoke.py \
       web/assets/schibsted-grotesk.woff2 web/assets/OFL.txt sample-docs/*.md"
if [ "${1:-}" != "api" ]; then files="$files web/index.html"; fi
for f in $files; do
  sprite file push -p "$f" "/home/sprite/roost/$f" >/dev/null
done
sprite exec --no-stdin -- sprite-env services restart roost >/dev/null
sprite exec --no-stdin -- sprite-env services get roost
