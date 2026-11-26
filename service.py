"""roost HTTP service. Stdlib only; runs as a Sprite service on port 8080.

Routes
  Page        GET /, GET /assets/*, GET /healthz
  Sign-in     POST /api/auth/start, POST /api/auth/verify, GET /auth?t=, POST /api/auth/signout
  Signed in   GET /api/me, /api/documents, /api/due, /api/ask
              POST /api/upload, /api/samples, /api/documents/<id>/delete, /api/sync,
                   /api/settings, /api/digest/test, /api/account/delete
  Owner       X-Roost-Token: POST /internal/sync-all, /internal/digest, /internal/delete-user

Signed-in requests use the `roost_session` cookie. Every POST under /api/ must
also send `X-Requested-With: roost`, which a cross-site form cannot do.
"""

import datetime as dt
import http.cookies
import json
import os
import re
import signal
import sys
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import accounts
import auth
import digest
import gateway
import mail
import inbox
import userspace
from box import Box
from nest import Nest

PORT = int(os.environ.get("PORT", "8080"))
MAX_QUESTION = 500
MAX_JSON = 8 * 1024
TEST_SENDS_PER_DAY = 3
COOKIE = "roost_session"
WEB = Path(__file__).resolve().parent / "web"
ASSETS = {"/assets/schibsted-grotesk.woff2": ("schibsted-grotesk.woff2", "font/woff2")}
PAGE_CSP = ("default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
            "font-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
            "form-action 'self'; frame-ancestors 'none'")

# Seams for tests: swap these for fakes.
make_box = Box
make_nest = Nest
send_mail = mail.send
make_inbox = inbox.AgentMailInbox

DELETE_PATH = re.compile(r"^/api/documents/(\d{1,20})/delete$")


def signin_email(code, token):
    link = f"{digest.PUBLIC_URL}/auth?t={urllib.parse.quote(token)}"
    text = (f"Your roost sign-in code is {code}\n\n"
            f"Or open this link to sign in:\n{link}\n\n"
            "The code and link work once and expire in 15 minutes. "
            "If you didn't ask to sign in, ignore this email.")
    html = ('<div style="font-family:Helvetica,Arial,sans-serif;color:#111;max-width:520px">'
            "<p>Your roost sign-in code is</p>"
            f'<p style="font-size:32px;font-weight:700;letter-spacing:4px;margin:8px 0">{code}</p>'
            f'<p><a href="{link}">Or sign in with this link</a></p>'
            '<p style="color:#777;font-size:13px">The code and link work once and expire in 15 minutes. '
            "If you didn't ask to sign in, ignore this email.</p></div>")
    return f"Your roost sign-in code: {code}", text, html


class Handler(BaseHTTPRequestHandler):
    # ---------- responses ----------

    def _send(self, status, body, content_type="text/plain; charset=utf-8", headers=None):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in (headers or {}).items():
            if isinstance(value, list):
                for v in value:
                    self.send_header(name, v)
            else:
                self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _json(self, status, obj, headers=None):
        self._send(status, json.dumps(obj, indent=2) + "\n", "application/json",
                   {"Cache-Control": "no-store", **(headers or {})})

    def _error(self, status, message):
        self._json(status, {"error": message})

    def _guarded(self, work, status=200, headers=None):
        """Run work() and reply with its JSON, mapping failures to HTTP errors."""
        try:
            result = work()
        except (accounts.SignInError, userspace.LimitError) as e:
            self._error(e.status, str(e))
        except mail.MailBudgetExceeded:
            self._error(503, "roost has sent all the email it can today. Try again tomorrow.")
        except gateway.GatewayError as e:
            print(f"gateway error: {e} {e.body[:300]}", file=sys.stderr, flush=True)
            self._json(502, {"error": "roost couldn't reach Box, Pinecone or email just now. Try again.",
                             "upstream_status": e.status})
        except LookupError as e:
            self._error(404, str(e))
        except Exception as e:  # keep the service up; log the trace for `services` logs
            traceback.print_exc()
            self._error(500, f"Something went wrong ({type(e).__name__}).")
        else:
            self._json(status, result, headers)

    # ---------- request helpers ----------

    def _query(self):
        return urllib.parse.parse_qs(self.path.partition("?")[2])

    def _body(self, limit):
        length = int(self.headers.get("Content-Length") or 0)
        if length > limit:
            self.close_connection = True
            raise userspace.LimitError("That is too large to send.", 413)
        return self.rfile.read(length) if length else b""

    def _json_body(self):
        try:
            data = json.loads(self._body(MAX_JSON) or b"{}")
        except ValueError:
            raise userspace.LimitError("That request wasn't valid JSON.") from None
        if not isinstance(data, dict):
            raise userspace.LimitError("That request wasn't valid JSON.")
        return data

    def _session_id(self):
        jar = http.cookies.SimpleCookie()
        try:
            jar.load(self.headers.get("Cookie") or "")
        except http.cookies.CookieError:
            return None
        return jar[COOKIE].value if COOKIE in jar else None

    def _user(self):
        """The signed-in uid, or reply 401 and return None."""
        uid = accounts.session_user(self._session_id())
        if not uid:
            self._error(401, "Please sign in.")
        return uid

    def _csrf_ok(self):
        if self.headers.get("X-Requested-With") != "roost":
            self._error(403, "Missing X-Requested-With header.")
            return False
        return True

    def _owner(self):
        failure = auth.check(self.headers.get(auth.HEADER))
        if failure:
            self._error(*failure)
            return False
        return True

    @staticmethod
    def _cookie(sid, max_age):
        return (f"{COOKIE}={sid}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age={max_age}")

    # ---------- GET ----------

    def do_GET(self):
        path = self.path.partition("?")[0]
        if path == "/":
            self._page()
        elif path == "/healthz":
            self._send(200, "ok\n")
        elif path in ASSETS:
            name, content_type = ASSETS[path]
            self._send(200, (WEB / "assets" / name).read_bytes(), content_type,
                       {"Cache-Control": "public, max-age=604800, immutable"})
        elif path == "/auth":
            self._auth_link()
        elif path == "/api/me":
            self._me()
        elif path == "/api/documents":
            uid = self._user()
            if uid:
                self._guarded(lambda: {"documents": userspace.documents(uid), "usage": userspace.usage(uid)})
        elif path == "/api/due":
            uid = self._user()
            if uid:
                days = self._query().get("days", ["60"])[0]
                days = max(1, min(int(days), 400)) if days.isdigit() else 60
                self._guarded(lambda: {"items": userspace.due(uid, within_days=days)})
        elif path == "/api/ask":
            uid = self._user()
            if uid:
                question = self._query().get("q", [""])[0].strip()
                if self._question_ok(question):
                    self._guarded(lambda: userspace.ask(uid, question, make_nest))
        else:
            self._error(404, "Not found.")

    def do_HEAD(self):
        path = self.path.partition("?")[0]
        if path in ("/", "/healthz") or path in ASSETS:
            self.do_GET()
        else:
            self._send(405, "", headers={"Allow": "GET"})

    def _page(self):
        # Read per request so a pushed page shows up without a restart.
        self._send(200, (WEB / "index.html").read_bytes(), "text/html; charset=utf-8", {
            "Cache-Control": "no-cache",
            "Content-Security-Policy": PAGE_CSP,
            "Referrer-Policy": "no-referrer",
        })

    def _question_ok(self, question):
        if not question:
            self._error(400, "Type a question first.")
            return False
        if len(question) > MAX_QUESTION:
            self._error(400, f"Questions can be up to {MAX_QUESTION} characters.")
            return False
        return True

    def _me(self):
        uid = accounts.session_user(self._session_id())
        if not uid:
            self._json(200, {"signed_in": False, "full": len(accounts.users()) >= accounts.MAX_USERS})
            return
        user = accounts.get_user(uid)
        self._guarded(lambda: {"signed_in": True, "email": user["email"],
                               "reminders": bool(user.get("reminders")), "usage": userspace.usage(uid)})

    def _auth_link(self):
        token = self._query().get("t", [""])[0]
        try:
            uid = accounts.verify_token(token)
        except accounts.SignInError:
            self._send(303, "", headers={"Location": "/?signin=expired"})
            return
        sid = accounts.create_session(uid)
        self._send(303, "", headers={"Location": "/", "Set-Cookie": self._cookie(sid, 30 * 86400)})

    # ---------- POST ----------

    def do_POST(self):
        path = self.path.partition("?")[0]
        if path.startswith("/api/"):
            if self._csrf_ok():
                self._api_post(path)
        elif path == "/internal/sync-all":
            if self._owner():
                self._guarded(_sync_all)
        elif path == "/internal/digest":
            if self._owner():
                self._guarded(lambda: digest.run(send_mail))
        elif path == "/internal/delete-user":
            if self._owner():
                self._guarded(self._owner_delete)
        else:
            self._error(404, "Not found.")

    def _api_post(self, path):
        if path == "/api/auth/start":
            def start():
                data = self._json_body()
                test = self.headers.get(auth.HEADER) is not None
                if test:  # the smoke test; a wrong token is refused, never treated as a normal sign-in
                    failure = auth.check(self.headers.get(auth.HEADER))
                    if failure:
                        raise accounts.SignInError(failure[1], failure[0])
                token, code = accounts.start_signin(data.get("email"), test=test)
                subject, text, html = signin_email(code, token)
                send_mail(accounts.normalise_email(data.get("email")), subject, text, html,
                          kind="test" if test else "user")
                return {"sent": True}
            self._guarded(start)
            return
        if path == "/api/auth/verify":
            data = {}
            try:
                data = self._json_body()
                uid = accounts.verify_code(data.get("email"), str(data.get("code", "")))
            except (accounts.SignInError, userspace.LimitError) as e:
                self._error(e.status, str(e))
                return
            sid = accounts.create_session(uid)
            self._json(200, {"signed_in": True}, {"Set-Cookie": self._cookie(sid, 30 * 86400)})
            return
        if path == "/api/auth/signout":
            accounts.end_session(self._session_id())
            self._json(200, {"signed_in": False}, {"Set-Cookie": self._cookie("", 0)})
            return

        uid = self._user()
        if not uid:
            return
        if path == "/api/upload":
            def upload():
                data = self._body(userspace.MAX_FILE_BYTES)
                name = urllib.parse.unquote(self.headers.get("X-Filename") or "")
                summary = userspace.upload(uid, name, data, make_box(), make_nest)
                return {"summary": _summary(summary), "documents": userspace.documents(uid),
                        "usage": userspace.usage(uid)}
            self._guarded(upload)
        elif path == "/api/samples":
            self._guarded(lambda: {"summary": _summary(userspace.add_samples(uid, make_box(), make_nest)),
                                   "documents": userspace.documents(uid), "usage": userspace.usage(uid)})
        elif DELETE_PATH.match(path):
            file_id = DELETE_PATH.match(path).group(1)
            self._guarded(lambda: {"documents": userspace.delete(uid, file_id, make_box(), make_nest),
                                   "usage": userspace.usage(uid)})
        elif path == "/api/sync":
            def sync():
                box = make_box()
                forwarded = inbox.poll(box, make_nest, make_inbox(), only_uid=uid).get(uid)
                return {"summary": _summary(userspace.sync(uid, box, make_nest)),
                        "forwarded": forwarded or {"added": [], "skipped": []},
                        "documents": userspace.documents(uid), "usage": userspace.usage(uid)}
            self._guarded(sync)
        elif path == "/api/settings":
            def settings():
                data = self._json_body()
                if not isinstance(data.get("reminders"), bool):
                    raise userspace.LimitError("Send reminders as true or false.")
                user = accounts.update_user(uid, reminders=data["reminders"])
                return {"reminders": user["reminders"]}
            self._guarded(settings)
        elif path == "/api/digest/test":
            self._guarded(lambda: _test_digest(uid))
        elif path == "/api/account/delete":
            self._guarded(lambda: {"deleted": True, **userspace.erase(uid, make_box(), make_nest)},
                          headers={"Set-Cookie": self._cookie("", 0)})
        else:
            self._error(404, "Not found.")

    def _owner_delete(self):
        """{"email": ...} erases one user; {"all": true} erases everyone (after judging)."""
        data = self._json_body()
        if data.get("all") is True:
            uids = list(accounts.users())
        else:
            uid = accounts.find_by_email(accounts.normalise_email(data.get("email")))
            if not uid:
                raise userspace.LimitError("There is no account with that email.", 404)
            uids = [uid]
        box = make_box()
        return {"deleted": [userspace.erase(uid, box, make_nest) for uid in uids]}



def _sync_all():
    """Read forwarded email, then re-read every user's documents; one failure doesn't stop the rest."""
    box, results = make_box(), {}
    try:
        forwarded = inbox.poll(box, make_nest, make_inbox())
    except Exception as e:
        print(f"inbox poll failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        forwarded = {}
    for uid in accounts.users():
        try:
            results[uid] = {**_summary(userspace.sync(uid, box, make_nest)),
                            "forwarded": len((forwarded.get(uid) or {}).get("added", []))}
        except Exception as e:
            print(f"sync {uid} failed: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            results[uid] = {"error": type(e).__name__}
    return results


def _summary(s):
    """The parts of an ingest summary the page shows."""
    return {k: s.get(k) for k in ("added", "updated", "unchanged", "removed", "skipped")}


def _test_digest(uid):
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    user = accounts.get_user(uid)
    sends = user.get("test_sends") or {}
    count = sends.get("count", 0) if sends.get("date") == today else 0
    if count >= TEST_SENDS_PER_DAY:
        raise userspace.LimitError(f"You can send yourself {TEST_SENDS_PER_DAY} test reminders a day.", 429)
    result = digest.send_for(uid, send_mail, force=True)
    if result == "sent":
        accounts.update_user(uid, test_sends={"date": today, "count": count + 1})
    return {"result": result, "email": user["email"]}


def main():
    # Exit 0 on SIGTERM so `sprite-env services stop` reads as stopped, not failed.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"roost listening on :{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
