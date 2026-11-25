"""roost HTTP service. Stdlib only; runs as a Sprite service on port 8080."""

import json
import os
import signal
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8080"))


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, content_type="text/plain; charset=utf-8"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status, obj):
        self._send(status, json.dumps(obj) + "\n", "application/json")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/healthz"):
            self._send(200, "ok\n")
        else:
            self._json(404, {"error": "not found", "path": path})


def main():
    # Exit 0 on SIGTERM so `sprite-env services stop` reads as stopped, not failed.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"roost listening on :{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
