"""Email through the AgentMail connector, with a daily budget.

AgentMail's free tier allows 100 emails a day in total. roost keeps its own
count per kind in data/mail_log.json: real users get DAILY_BUDGET, the owner's
smoke tests get their own TEST_BUDGET, so tests never use up what users need.
Together they stay under the provider's 100.
"""

import datetime as dt
import os
import threading
import urllib.parse

import gateway
from store import read_json, write_json

INBOX = os.environ.get("ROOST_INBOX", "roost-nest@agentmail.to")
DAILY_BUDGET = int(os.environ.get("ROOST_MAIL_BUDGET", "90"))
TEST_BUDGET = int(os.environ.get("ROOST_TEST_MAIL_BUDGET", "8"))
BUDGETS = {"user": DAILY_BUDGET, "test": TEST_BUDGET}

_lock = threading.Lock()


class MailBudgetExceeded(Exception):
    pass


def _log_path():
    from ingest import data_dir
    return data_dir() / "mail_log.json"


def _counts(entry):
    """A day's counts; older logs stored one number, all of it user mail."""
    return entry if isinstance(entry, dict) else {"user": entry or 0}


def sent_today(today=None, kind="user"):
    today = (today or dt.datetime.now(dt.timezone.utc).date()).isoformat()
    return _counts(read_json(_log_path(), {}).get(today)).get(kind, 0)


def send(to, subject, text, html=None, today=None, kind="user"):
    """Send one email from the roost inbox. `kind` is "user" or "test"; each has its
    own daily budget. Raises MailBudgetExceeded past it."""
    if kind not in BUDGETS:
        raise ValueError(f"unknown mail kind {kind!r}")
    day = (today or dt.datetime.now(dt.timezone.utc).date()).isoformat()
    with _lock:
        log = read_json(_log_path(), {})
        if _counts(log.get(day)).get(kind, 0) >= BUDGETS[kind]:
            raise MailBudgetExceeded(f"daily {kind} email budget of {BUDGETS[kind]} reached")
        body = {"to": [to], "subject": subject, "text": text}
        if html:
            body["html"] = html
        inbox = urllib.parse.quote(INBOX, safe="@.")
        gateway.request("POST", f"{gateway.base_url('agentmail')}/v0/inboxes/{inbox}/messages/send", body)
        log = {k: v for k, v in log.items() if k >= (dt.date.fromisoformat(day) - dt.timedelta(days=7)).isoformat()}
        counts = _counts(log.get(day))
        counts[kind] = counts.get(kind, 0) + 1
        log[day] = counts
        write_json(_log_path(), log)
