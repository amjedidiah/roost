#!/bin/sh
# Push the service code to the Sprite and restart it. Run from the repo root.
set -eu
cd "$(dirname "$0")/.."
for f in service.py auth.py gateway.py box.py nest.py ingest.py; do
  sprite file push "$f" "/home/sprite/roost/$f"
done
sprite exec --no-stdin -- sprite-env services restart roost >/dev/null
sprite exec --no-stdin -- sprite-env services get roost
