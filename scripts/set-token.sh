#!/bin/sh
# Create the roost shared secret (if .env has none) and install its SHA-256 on the Sprite.
# The token itself stays in the local .env as ROOST_TOKEN and is never printed or uploaded.
# To rotate: delete the ROOST_TOKEN line from .env and run this again.
set -eu
cd "$(dirname "$0")/.."
hash=$(python3 - <<'PY'
import hashlib, secrets
from pathlib import Path
env = Path(".env")
text = env.read_text() if env.exists() else ""
token = next((l.split("=", 1)[1].strip() for l in text.splitlines() if l.startswith("ROOST_TOKEN=")), "")
if not token:
    token = secrets.token_urlsafe(32)
    sep = "" if not text or text.endswith("\n") else "\n"
    with env.open("a") as f:
        f.write(f"{sep}ROOST_TOKEN={token}\n")
print(hashlib.sha256(token.encode()).hexdigest())
PY
)
sprite exec --no-stdin -- sh -c "mkdir -p /home/sprite/roost/data && umask 077 && printf '%s\n' '$hash' > /home/sprite/roost/data/token.sha256"
echo "Installed token hash on the Sprite. Send the token from .env in the X-Roost-Token header."
