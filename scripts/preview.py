"""Local preview of the web page, before deploying it.

Serves web/index.html and web/assets/ from this working copy, and forwards the
API calls (/ask, /nest, /ingest, /healthz) to the live Sprite, because Box and
Pinecone are only reachable from inside the Sprite. The page you see is local;
the answers are real.

    python3 scripts/preview.py            # http://127.0.0.1:8765
    ROOST_URL=https://... PORT=9000 python3 scripts/preview.py

Paste your access code (ROOST_TOKEN from .env) into the page once; the browser
keeps it for this origin. Note that Refresh from Box runs a real ingest.
"""

import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "web"
UPSTREAM = os.environ.get("ROOST_URL", "https://roost-b6xbd.sprites.app").rstrip("/")
PORT = int(os.environ.get("PORT", "8765"))
API = ("/api/", "/auth", "/internal/", "/ask", "/nest", "/ingest", "/healthz")
FORWARD = {"x-roost-token", "x-requested-with", "x-filename", "content-type", "cookie"}
TYPES = {".html": "text/html; charset=utf-8", ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8"}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # hand redirects (sign-in links) back to the browser


_opener = urllib.request.build_opener(_NoRedirect)


def _passthrough(headers):
    """Cookies and redirects from the Sprite, made to work on http://localhost."""
    out = [("Set-Cookie", c.replace("; Secure", "")) for c in headers.get_all("Set-Cookie") or []]
    if headers.get("Location"):
        out.append(("Location", headers["Location"]))
    return out


class Preview(BaseHTTPRequestHandler):
    def _reply(self, status, body, content_type, extra=()):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        for name, value in extra:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _forward(self):
        length = int(self.headers.get("Content-Length") or 0)
        req = urllib.request.Request(
            UPSTREAM + self.path,
            data=self.rfile.read(length) if length else None,
            method=self.command,
            headers={k: v for k, v in self.headers.items() if k.lower() in FORWARD},
        )
        try:
            with _opener.open(req, timeout=120) as r:
                self._reply(r.status, r.read(), r.headers.get("Content-Type", "application/json"), _passthrough(r.headers))
        except urllib.error.HTTPError as e:
            self._reply(e.code, e.read(), e.headers.get("Content-Type", "application/json"), _passthrough(e.headers))
        except urllib.error.URLError as e:
            self._reply(502, f'{{"error": "preview could not reach {UPSTREAM}: {e.reason}"}}'.encode(),
                        "application/json")

    def do_GET(self):
        path = self.path.partition("?")[0]
        if path.startswith(API):
            return self._forward()
        local = ROOT / ("index.html" if path == "/" else path.lstrip("/"))
        if local.resolve().is_relative_to(ROOT) and local.is_file():  # no path escapes
            return self._reply(200, local.read_bytes(), TYPES.get(local.suffix, "application/octet-stream"))
        self._reply(404, b'{"error": "not found"}', "application/json")

    def do_POST(self):
        if self.path.partition("?")[0].startswith(API):
            return self._forward()
        self._reply(404, b'{"error": "not found"}', "application/json")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Preview)
    print(f"roost preview on http://127.0.0.1:{PORT} (API -> {UPSTREAM})", flush=True)
    server.serve_forever()
