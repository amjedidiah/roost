"""Shared-secret check for the protected endpoints.

Clients send the token in the X-Roost-Token header. The Sprite stores only the
token's SHA-256 (data/token.sha256), never the token itself. With no hash file,
every protected request is refused: the service fails closed.
"""

import hashlib
import hmac

from ingest import data_dir

HEADER = "X-Roost-Token"


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def hash_path():
    return data_dir() / "token.sha256"


def check(provided, path=None):
    """Return None if `provided` is valid, else (status, message)."""
    try:
        expected = (path or hash_path()).read_text().strip()
    except FileNotFoundError:
        expected = ""
    if not expected:
        return 503, "auth is not configured on this Sprite (run scripts/set-token.sh)"
    if not provided:
        return 401, f"missing {HEADER} header"
    if not hmac.compare_digest(token_hash(provided), expected):
        return 403, "invalid token"
    return None
