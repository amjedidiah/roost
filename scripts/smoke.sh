#!/bin/sh
# Run the live smoke test on the Sprite (once per deployed code version; --force to repeat).
# ROOST_TOKEN from the local .env goes over stdin for this one run; it is never written on the Sprite.
set -eu
cd "$(dirname "$0")/.."
token=$(sed -n 's/^ROOST_TOKEN=//p' .env 2>/dev/null | head -1)
if [ -z "$token" ]; then
  echo "ROOST_TOKEN is missing from .env (run ./scripts/set-token.sh)." >&2
  exit 1
fi
printf '%s\n' "$token" | sprite exec --stdin -- sh -c "cd /home/sprite/roost && python3 scripts/smoke.py $*"
