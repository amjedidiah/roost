"""roost HTTP service. Stdlib only; runs as a Sprite service on port 8080."""

import json
import os
import signal
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import auth
import gateway
from box import Box
from ingest import ingest
from nest import Nest

PORT = int(os.environ.get("PORT", "8080"))

_ingest_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, content_type="text/plain; charset=utf-8"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status, obj):
        self._send(status, json.dumps(obj, indent=2) + "\n", "application/json")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/healthz"):
            self._send(200, "ok\n")
        else:
            self._json(404, {"error": "not found", "path": path})

    def _authorized(self):
        failure = auth.check(self.headers.get(auth.HEADER))
        if failure:
            self._json(failure[0], {"error": failure[1]})
            return False
        return True

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/ingest":
            if self._authorized():
                self._ingest()
        else:
            self._json(404, {"error": "not found", "path": path})

    def _ingest(self):
        if not _ingest_lock.acquire(blocking=False):
            self._json(409, {"error": "an ingest is already running"})
            return
        try:
            self._json(200, ingest(Box(), Nest()))
        except gateway.GatewayError as e:
            self._json(502, {"error": str(e), "upstream_status": e.status, "detail": e.body})
        except LookupError as e:
            self._json(404, {"error": str(e)})
        except Exception as e:  # keep the service up; log the trace for `services` logs
            traceback.print_exc()
            self._json(500, {"error": f"{type(e).__name__}: {e}"})
        finally:
            _ingest_lock.release()


def main():
    # Exit 0 on SIGTERM so `sprite-env services stop` reads as stopped, not failed.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"roost listening on :{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
