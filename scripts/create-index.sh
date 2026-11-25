#!/bin/sh
# Create the plain dense Pinecone index roost uses (run once, on your laptop).
# Reads PINECONE_API_KEY from .env; the key never goes to the Sprite.
# Why not the console: it now makes indexes with a document schema, which the
# Sprites connector can't search. Why not the connector: it can't create indexes.
set -eu
cd "$(dirname "$0")/.."
INDEX="${1:-roost-nest}" python3 - <<'PY'
import json, os, urllib.error, urllib.request
key = next((l.split("=", 1)[1].strip().strip("\"'") for l in open(".env") if l.startswith("PINECONE_API_KEY=")), "")
if not key:
    raise SystemExit("PINECONE_API_KEY is not set in .env")
body = {"name": os.environ["INDEX"], "dimension": 1024, "metric": "cosine", "vector_type": "dense",
        "spec": {"serverless": {"cloud": "aws", "region": "us-east-1"}}, "deletion_protection": "disabled"}
req = urllib.request.Request("https://api.pinecone.io/indexes", data=json.dumps(body).encode(), method="POST",
                             headers={"Api-Key": key, "Content-Type": "application/json",
                                      "X-Pinecone-API-Version": "2025-04"})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        print(f"created index {json.load(r)['name']}")
except urllib.error.HTTPError as e:
    raise SystemExit(f"HTTP {e.code}: {e.read().decode()[:300]}")
PY
