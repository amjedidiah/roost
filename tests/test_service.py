import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from auth import token_hash


class ServiceRoutesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.data = Path(cls.tmp.name)
        cls._old_data = os.environ.get("ROOST_DATA")
        os.environ["ROOST_DATA"] = str(cls.data)
        (cls.data / "token.sha256").write_text(token_hash("t0ken") + "\n")
        (cls.data / "nest.json").write_text(json.dumps({"files": {
            "2": {"name": "b.md", "sha1": "x", "chunks": 3},
            "1": {"name": "a.md", "sha1": "y", "chunks": 2},
        }}))
        import service
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), service.Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        if cls._old_data is None:
            os.environ.pop("ROOST_DATA", None)
        else:
            os.environ["ROOST_DATA"] = cls._old_data
        cls.tmp.cleanup()

    def get(self, path, token=None, method="GET"):
        req = urllib.request.Request(self.base + path, method=method,
                                     headers={"X-Roost-Token": token} if token else {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def test_page_is_served_with_csp(self):
        status, headers, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Type"].startswith("text/html"))
        self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
        self.assertIn(b"Never miss what your documents say is due.", body)

    def test_font_asset(self):
        status, headers, body = self.get("/assets/schibsted-grotesk.woff2")
        self.assertEqual((status, headers["Content-Type"]), (200, "font/woff2"))
        self.assertEqual(body[:4], b"wOF2")

    def test_healthz_stays_plain(self):
        self.assertEqual(self.get("/healthz")[2], b"ok\n")

    def test_nest_requires_token_and_lists_files(self):
        self.assertEqual(self.get("/nest")[0], 401)
        self.assertEqual(self.get("/nest", "wrong")[0], 403)
        status, _, body = self.get("/nest", "t0ken")
        self.assertEqual(status, 200)
        nest = json.loads(body)
        self.assertEqual((nest["count"], nest["chunks"]), (2, 5))
        self.assertEqual([f["name"] for f in nest["files"]], ["a.md", "b.md"])

    def test_head_only_on_static_routes(self):
        self.assertEqual(self.get("/", method="HEAD")[0], 200)
        self.assertEqual(self.get("/ask?q=x", "t0ken", method="HEAD")[0], 405)

    def test_unknown_path(self):
        self.assertEqual(self.get("/admin")[0], 404)


if __name__ == "__main__":
    unittest.main()
