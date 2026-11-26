"""Forward a bill: email sent to the roost inbox becomes a document.

Someone signed in to roost can forward an email (a bill, a booking, a letter)
from their sign-in address to roost-nest@agentmail.to. The next time roost
checks (their "Check for changes" button, or the daily run), the email's text
is saved as a .txt document in their space and read like any upload, so its
dates show up in Coming up and in reminders. Limits still apply.

Only the email's text is read. The AgentMail connector doesn't forward the
attachment endpoints and the Sprite holds no AgentMail key, so a bill sent as
an attachment has to be uploaded instead; the result says so.

Senders are matched to accounts by their From address. Email from an address
with no account is ignored. Email roost sends to itself (sign-in codes,
reminders to the test account) is ignored, except messages whose subject starts
with "roost-smoke:", which the smoke test uses to check this path; those count
only for SMOKE_MAX_AGE, so one run's leftover can't land in a later run.

Processed message ids are kept in data/inbox.json so nothing is added twice.
"""

import datetime as dt
import html.parser
import re
import threading
import urllib.parse
from email.utils import parseaddr

import accounts
import userspace
from ingest import data_dir
from mail import INBOX
from store import read_json, write_json

SMOKE_PREFIX = "roost-smoke:"
SMOKE_MAX_AGE = dt.timedelta(minutes=30)
MIN_TEXT = 20          # shorter bodies are treated as empty
KEEP_DONE = 2000       # remembered message ids
PAGE = 50
_lock = threading.Lock()


class AgentMailInbox:
    """The roost inbox through the connector gateway (list and get only)."""

    def __init__(self):
        import gateway
        self.gateway = gateway
        self.base = f"{gateway.base_url('agentmail')}/v0/inboxes/{urllib.parse.quote(INBOX, safe='@.')}/messages"

    def recent(self):
        """Received messages, newest first: [{"message_id", "from", "subject", ...}]."""
        return self.gateway.request("GET", f"{self.base}?limit={PAGE}&labels=received").get("messages", [])

    def get(self, message_id):
        return self.gateway.request("GET", f"{self.base}/{urllib.parse.quote(message_id, safe='@')}")


class _Text(html.parser.HTMLParser):
    BREAKS = {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "table"}

    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in self.BREAKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
        elif tag in self.BREAKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(markup):
    parser = _Text()
    parser.feed(markup or "")
    text = "".join(parser.parts)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def body_text(message):
    text = (message.get("text") or "").strip()
    if len(text) < MIN_TEXT and message.get("html"):
        text = html_to_text(message["html"])
    return text.replace("\r\n", "\n")


FWD = re.compile(r"^\s*((fwd?|fw|re)\s*:\s*)+", re.I)


def document_name(subject, when):
    subject = (subject or "")
    if subject.lower().startswith(SMOKE_PREFIX):
        subject = subject[len(SMOKE_PREFIX):]
    subject = FWD.sub("", subject).strip()
    subject = re.sub(r"[^\w .,()&'+-]", " ", subject)
    subject = re.sub(r"\s+", " ", subject).strip(" .")[:80]
    return f"{subject or 'Forwarded email ' + (when or '')[:10]}.txt".strip()


def sender(message):
    return parseaddr(message.get("from") or "")[1].strip().lower()


def _age(message, now):
    try:
        sent = dt.datetime.fromisoformat((message.get("timestamp") or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    return now - sent if sent.tzinfo else None


def _owner(message, now):
    """The uid an inbox message belongs to, or None."""
    address = sender(message)
    if not address:
        return None
    if address == INBOX.lower():
        if not (message.get("subject") or "").lower().startswith(SMOKE_PREFIX):
            return None  # roost's own mail
        age = _age(message, now)
        if age is None or age > SMOKE_MAX_AGE:
            return None  # a smoke test's leftover
    return accounts.find_by_email(address)


def _state_path():
    return data_dir() / "inbox.json"


def poll(box, make_nest, client=None, only_uid=None, now=None):
    """Turn new forwarded emails into documents.

    With `only_uid`, only that user's emails are processed; other users' emails
    wait for their own check or the daily run. Returns {uid: {"added": [...],
    "skipped": [{"name", "reason"}]}} for users who had email."""
    client = client or AgentMailInbox()
    now = now or dt.datetime.now(dt.timezone.utc)
    results = {}
    with _lock:
        state = read_json(_state_path(), {"done": []})
        done = set(state["done"])
        newly_done = []
        for item in client.recent():
            mid = item.get("message_id")
            if not mid or mid in done:
                continue
            uid = _owner(item, now)
            if only_uid is not None and uid is not None and uid != only_uid:
                continue
            newly_done.append(mid)
            if uid is None:
                continue
            result = results.setdefault(uid, {"added": [], "skipped": []})
            message = client.get(mid)
            name = document_name(message.get("subject"), message.get("timestamp"))
            if message.get("attachments"):
                result["skipped"].append({"name": ", ".join(a.get("filename") or "attachment"
                                                            for a in message["attachments"]),
                                          "reason": "roost can't open email attachments. Upload the file instead."})
            text = body_text(message)
            if len(text) < MIN_TEXT:
                if not message.get("attachments"):
                    result["skipped"].append({"name": name, "reason": "The email had no text to read."})
                continue
            try:
                userspace.upload(uid, name, text.encode("utf-8"), box, make_nest)
                result["added"].append(name)
            except userspace.LimitError as e:
                result["skipped"].append({"name": name, "reason": str(e)})
        if newly_done:
            state["done"] = (state["done"] + newly_done)[-KEEP_DONE:]
            write_json(_state_path(), state)
    return results
