"""Sprites connector gateway: discover connections and make keyless HTTP calls.

Only works on a Sprite. The gateway identifies the Sprite by its Fly request
signature, so no auth header is ever sent and no credential lives on the box.
"""

import json
import socket
import time
import urllib.error
import urllib.request

GATEWAY_LIST_URL = "https://api.sprites.dev/v1/gateway/list"
TIMEOUT = 60
RETRY_STATUSES = {502, 503, 504}  # the gateway returns these now and then; GETs are retried
RETRY_WAITS = (1, 3)

_base_urls = {}  # provider -> gateway_base_url. RAM cache only; rebuilt after a restart.


class GatewayError(Exception):
    def __init__(self, message, status=None, body=""):
        super().__init__(message)
        self.status = status
        self.body = body


def request(method, url, body=None, headers=None, raw=False, timeout=TIMEOUT):
    """Send a request. JSON-encodes `body` when it is not bytes. Returns parsed
    JSON, or bytes when `raw` is true."""
    headers = dict(headers or {})
    data = None
    if body is not None:
        if isinstance(body, (bytes, bytearray)):
            data = bytes(body)
        else:
            data = json.dumps(body).encode()
            headers.setdefault("Content-Type", "application/json")
    waits = RETRY_WAITS if method == "GET" else ()
    for attempt in range(len(waits) + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = resp.read()
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            if e.code in RETRY_STATUSES and attempt < len(waits):
                time.sleep(waits[attempt])
                continue
            raise GatewayError(f"{method} {url} -> {e.code}", e.code, detail) from None
        except urllib.error.URLError as e:
            raise GatewayError(f"{method} {url} failed: {e.reason}") from None
        except (TimeoutError, socket.timeout):
            raise GatewayError(f"{method} {url} timed out") from None
    if raw:
        return payload
    return json.loads(payload) if payload else {}


def base_url(provider):
    """Return the gateway base URL for a granted connection, e.g. 'box'."""
    if provider not in _base_urls:
        listing = request("GET", GATEWAY_LIST_URL)
        for conn in listing.get("connections", []):
            _base_urls.setdefault(conn.get("provider"), conn.get("gateway_base_url"))
        if provider not in _base_urls:
            raise GatewayError(
                f"no '{provider}' connection is granted to this Sprite; "
                "check the connector's access configuration in the Fly dashboard"
            )
    return _base_urls[provider]
