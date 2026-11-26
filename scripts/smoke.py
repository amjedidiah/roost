"""Live smoke test, run on the Sprite: one real pass through roost, then it cleans up.

Signs in as the roost inbox (roost-nest@agentmail.to) so the code email can be read
back through the AgentMail connector, then checks samples, due, upload, ask, a test
reminder, delete and sign-out, and finally deletes its own account, so no user slot,
Box content, vectors or session is left behind. It sends 2 emails.

The owner token arrives on stdin (never stored on the Sprite) and goes with the
sign-in request, which marks it as a test: it skips the sign-in rate limits and
the user cap without counting towards them, and its emails use the separate test
budget. So a smoke run never reduces what real users can do.

It runs once per deployed code version (a hash of the code on the Sprite); pass
--force to run again. Run it with ./scripts/smoke.sh from the laptop.
"""

import hashlib
import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import gateway  # noqa: E402
from ingest import data_dir  # noqa: E402
from digest import PUBLIC_URL  # noqa: E402
from mail import INBOX  # noqa: E402
from store import read_json, write_json  # noqa: E402

BASE = PUBLIC_URL.rstrip("/")  # https, so the Secure session cookie comes back
STAMP = data_dir() / "smoke.json"

_jar = http.cookiejar.CookieJar()
_open = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar)).open


def code_hash():
    h = hashlib.sha256()
    for p in sorted([*ROOT.glob("*.py"), ROOT / "web" / "index.html"]):
        if p.is_file():
            h.update(p.name.encode() + b"\0" + p.read_bytes())
    return h.hexdigest()[:16]


def call(method, path, body=None, raw=None, headers=None):
    h = {"X-Requested-With": "roost", **(headers or {})}
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    if body is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with _open(req, timeout=120) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def wait_for_email(subject_has, after):
    url = gateway.base_url("agentmail") + f"/v0/inboxes/{INBOX}/messages?limit=10"
    for _ in range(20):
        for m in gateway.request("GET", url).get("messages", []):
            if (subject_has in (m.get("subject") or "") and m.get("timestamp", "") > after
                    and "received" in m.get("labels", [])):
                return m
        time.sleep(3)
    return None


def stamp():
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 5))


class Smoke:
    def __init__(self, token):
        self.token = token
        self.failures = []

    def check(self, name, ok, detail=""):
        print(f"{'ok  ' if ok else 'FAIL'} {name}{'  ' + str(detail) if detail and not ok else ''}", flush=True)
        if not ok:
            self.failures.append(name)
        return ok

    def run(self):
        t0 = stamp()
        status, _ = call("POST", "/api/auth/start", {"email": INBOX}, headers={"X-Roost-Token": self.token})
        if not self.check("sign-in email requested", status == 200, status):
            return
        m = wait_for_email("sign-in code", t0)
        found = m and re.search(r"(\d{6})", m.get("subject", ""))
        if not self.check("code email arrived", bool(found)):
            return
        status, _ = call("POST", "/api/auth/verify", {"email": INBOX, "code": found.group(1)})
        if not self.check("code signs in", status == 200, status):
            return
        try:
            self.signed_in()
        finally:
            status, body = call("POST", "/api/account/delete")
            self.check("test account deleted", status == 200 and body.get("deleted"), (status, body))
            self.check("signed out after delete", call("GET", "/api/me")[1].get("signed_in") is False)

    def signed_in(self):
        status, body = call("GET", "/api/me")
        self.check("me", status == 200 and body.get("email") == INBOX, (status, body))
        status, body = call("POST", "/api/samples")
        self.check("samples added", status == 200 and len(body.get("documents", [])) == 8, (status, body))
        status, body = call("GET", "/api/due?days=400")
        self.check("due list has items", status == 200 and len(body.get("items", [])) > 0, (status, body))
        status, body = call("POST", "/api/upload", raw=b"# Bills\n\n## To do\n\n- Pay the electricity bill by 3 December\n",
                            headers={"X-Filename": "smoke-bills.md"})
        names = [d["name"] for d in body.get("documents", [])] if status == 200 else []
        self.check("upload", "smoke-bills.md" in names, (status, body))
        status, body = call("GET", "/api/ask?q=" + urllib.parse.quote("when do I pay the electricity bill"))
        self.check("ask finds the upload", status == 200 and body.get("source_file") == "smoke-bills.md", (status, body))
        t1 = stamp()
        status, body = call("POST", "/api/digest/test")
        self.check("test reminder sent", status == 200 and body.get("result") == "sent", (status, body))
        self.check("reminder email arrived", bool(wait_for_email("due soon", t1)))
        doc = next((d for d in call("GET", "/api/documents")[1].get("documents", []) if d["name"] == "smoke-bills.md"), None)
        if doc:
            status, body = call("POST", f"/api/documents/{doc['id']}/delete")
            self.check("delete one document", status == 200 and "smoke-bills.md" not in [d["name"] for d in body["documents"]],
                       (status, body))


def main():
    version = code_hash()
    last = read_json(STAMP, {})
    if last.get("code") == version and "--force" not in sys.argv:
        print(f"Already smoke-tested this code version ({version}) at {last.get('at')}: "
              f"{'passed' if last.get('passed') else 'FAILED'}. Use --force to run again (sends 2 emails).")
        return 0 if last.get("passed") else 1
    token = sys.stdin.readline().strip()
    if not token:
        print("No owner token on stdin. Run ./scripts/smoke.sh from the laptop.")
        return 2
    smoke = Smoke(token)
    smoke.run()
    passed = not smoke.failures
    write_json(STAMP, {"code": version, "at": stamp(), "passed": passed, "failures": smoke.failures})
    print("PASSED" if passed else f"FAILED: {', '.join(smoke.failures)}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
