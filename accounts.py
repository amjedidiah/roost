"""Accounts: email sign-in (link + 6-digit code), sessions, and limits.

No passwords. Every secret (sign-in token, code, session id) is random, sent to
the user once, and stored only as its SHA-256. All state lives in JSON files in
data/ and every change happens under one lock.
"""

import datetime as dt
import hashlib
import hmac
import os
import re
import secrets
import threading

from store import read_json, write_json

MAX_USERS = int(os.environ.get("ROOST_MAX_USERS", "40"))
SIGNIN_TTL = dt.timedelta(minutes=15)
SESSION_TTL = dt.timedelta(days=30)
MAX_CODE_ATTEMPTS = 5
PER_EMAIL_PER_HOUR = 3
GLOBAL_PER_HOUR = 20

EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")

_lock = threading.Lock()


class SignInError(Exception):
    """A sign-in step was refused; the message is safe to show to the user."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _h(secret):
    return hashlib.sha256(secret.encode()).hexdigest()


def _paths():
    from ingest import data_dir
    d = data_dir()
    return d / "accounts.json", d / "signin.json", d / "sessions.json"


def normalise_email(email):
    email = (email or "").strip().lower()
    if len(email) > 254 or not EMAIL.match(email):
        raise SignInError("That doesn't look like an email address.")
    return email


# --- users ---------------------------------------------------------------------

def _users():
    return read_json(_paths()[0], {"users": {}})


def users():
    """{uid: user} for every account."""
    return _users()["users"]


def get_user(uid):
    return users().get(uid)


def find_by_email(email):
    for uid, user in users().items():
        if user["email"] == email:
            return uid
    return None


def update_user(uid, **changes):
    with _lock:
        data = _users()
        data["users"][uid].update(changes)
        write_json(_paths()[0], data)
        return data["users"][uid]


def delete_user(uid):
    """Remove the account and every session it has, and void its pending sign-ins. Returns the old record."""
    with _lock:
        accounts_path, signin_path, sessions_path = _paths()
        data = _users()
        user = data["users"].pop(uid, None)
        if user is None:
            return None
        write_json(accounts_path, data)
        write_json(sessions_path, {k: v for k, v in read_json(sessions_path, {}).items() if v["uid"] != uid})
        # Keep pending sign-ins (hashes only, gone within the hour) so deleting an account
        # doesn't reset the per-email rate limit; just make them unusable.
        pending = read_json(signin_path, [])
        for r in pending:
            if r["email"] == user["email"]:
                r["used"] = True
        write_json(signin_path, pending)
        return user


def _create_user(email, now, test=False):
    data = _users()
    if not test and len(data["users"]) >= MAX_USERS:
        raise SignInError("roost is full right now. It is a small demo with room for "
                          f"{MAX_USERS} people.", 403)
    uid = secrets.token_hex(6)
    data["users"][uid] = {"email": email, "created": now.isoformat(timespec="seconds"),
                          "reminders": not test, "last_digest": None}
    if test:
        data["users"][uid]["test"] = True
    write_json(_paths()[0], data)
    return uid


# --- sign-in ---------------------------------------------------------------------

def start_signin(email, now=None, test=False):
    """Create a one-time link token and 6-digit code for `email`.
    Returns (token, code) to email to the user. Raises SignInError.

    `test` is only for sign-ins the caller has verified with the owner token (the
    smoke test): they skip the hourly limits and the user cap, and don't count
    towards them, so tests never reduce what real users can do."""
    now = now or _now()
    email = normalise_email(email)
    with _lock:
        path = _paths()[1]
        pending = [r for r in read_json(path, []) if dt.datetime.fromisoformat(r["created"]) > now - dt.timedelta(hours=1)]
        counted = [r for r in pending if not r.get("test")]
        if not test and sum(r["email"] == email for r in counted) >= PER_EMAIL_PER_HOUR:
            raise SignInError("Too many sign-in emails for this address. Wait an hour, or use the code "
                              "from the last email.", 429)
        if not test and len(counted) >= GLOBAL_PER_HOUR:
            raise SignInError("roost is busy. Try again in a few minutes.", 429)
        if not test and find_by_email(email) is None and len(users()) >= MAX_USERS:
            raise SignInError(f"roost is full right now. It is a small demo with room for {MAX_USERS} people.", 403)
        token, code = secrets.token_urlsafe(32), f"{secrets.randbelow(10**6):06d}"
        pending.append({"email": email, "token": _h(token), "code": _h(email + ":" + code),
                        "created": now.isoformat(), "attempts": 0, "used": False, "test": test})
        write_json(path, pending)
    return token, code


def _complete(record, now):
    record["used"] = True
    uid = find_by_email(record["email"]) or _create_user(record["email"], now, record.get("test", False))
    return uid


def verify_token(token, now=None):
    """Sign in with the link token. Returns uid. Raises SignInError."""
    now = now or _now()
    with _lock:
        path = _paths()[1]
        pending = read_json(path, [])
        digest = _h(token or "")
        for r in pending:
            if hmac.compare_digest(r["token"], digest):
                if r["used"] or dt.datetime.fromisoformat(r["created"]) < now - SIGNIN_TTL:
                    raise SignInError("This sign-in link has expired. Ask for a new one.", 400)
                uid = _complete(r, now)
                write_json(path, pending)
                return uid
    raise SignInError("This sign-in link isn't valid. Ask for a new one.", 400)


def verify_code(email, code, now=None):
    """Sign in with email + 6-digit code. Returns uid. Raises SignInError."""
    now = now or _now()
    email = normalise_email(email)
    code = re.sub(r"\D", "", code or "")
    with _lock:
        path = _paths()[1]
        pending = read_json(path, [])
        live = [r for r in pending if r["email"] == email and not r["used"]
                and dt.datetime.fromisoformat(r["created"]) > now - SIGNIN_TTL]
        if not live:
            raise SignInError("That code has expired. Ask for a new one.", 400)
        latest = live[-1]
        latest["attempts"] += 1
        ok = latest["attempts"] <= MAX_CODE_ATTEMPTS and hmac.compare_digest(latest["code"], _h(email + ":" + code))
        if ok:
            uid = _complete(latest, now)
            write_json(path, pending)
            return uid
        write_json(path, pending)
        if latest["attempts"] >= MAX_CODE_ATTEMPTS:
            raise SignInError("Too many wrong codes. Ask for a new one.", 429)
        raise SignInError("That code isn't right. Check the email and try again.", 400)


# --- sessions --------------------------------------------------------------------

def create_session(uid, now=None):
    now = now or _now()
    sid = secrets.token_urlsafe(32)
    with _lock:
        path = _paths()[2]
        sessions = {k: v for k, v in read_json(path, {}).items()
                    if dt.datetime.fromisoformat(v["expires"]) > now}
        sessions[_h(sid)] = {"uid": uid, "expires": (now + SESSION_TTL).isoformat()}
        write_json(path, sessions)
    return sid


def session_user(sid, now=None):
    """The uid for a live session id, or None."""
    if not sid:
        return None
    now = now or _now()
    entry = read_json(_paths()[2], {}).get(_h(sid))
    if not entry or dt.datetime.fromisoformat(entry["expires"]) <= now:
        return None
    return entry["uid"] if get_user(entry["uid"]) else None


def end_session(sid):
    with _lock:
        path = _paths()[2]
        sessions = read_json(path, {})
        sessions.pop(_h(sid or ""), None)
        write_json(path, sessions)
