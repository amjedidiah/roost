"""The daily reminder email: what each user has due in the next 7 days."""

import datetime as dt
import html
import os

import accounts
import userspace

PUBLIC_URL = os.environ.get("ROOST_PUBLIC_URL", "https://roost-b6xbd.sprites.app")
WINDOW_DAYS = 7
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _when(item):
    d = dt.date.fromisoformat(item["due"])
    label = f"{d.strftime('%a')} {d.day} {MONTHS[d.month - 1]}"
    days = item["days"]
    rel = ("today" if days == 0 else "tomorrow" if days == 1 else f"in {days} days" if days > 1
           else "yesterday" if days == -1 else f"{-days} days ago")
    return f"{label} ({rel})"


def compose(items):
    """(subject, text, html) for a list of due items."""
    overdue = [i for i in items if i["overdue"]]
    soon = [i for i in items if not i["overdue"]]
    n = len(items)
    subject = f"roost: {n} thing{'s' if n != 1 else ''} due soon"
    if overdue:
        subject += f" ({len(overdue)} overdue)"

    lines = ["Here is what your documents say is due.", ""]
    parts = ['<div style="font-family:Helvetica,Arial,sans-serif;color:#111;max-width:560px">',
             "<p>Here is what your documents say is due.</p>"]
    for title, group in (("Overdue", overdue), ("Next 7 days", soon)):
        if not group:
            continue
        lines.append(title.upper())
        parts.append(f'<h3 style="margin:20px 0 8px">{title}</h3><ul style="padding-left:18px">')
        for i in group:
            lines.append(f"- {i['line']}")
            lines.append(f"  Due {_when(i)} · from {i['file']}")
            parts.append(f'<li style="margin-bottom:10px"><b>{html.escape(i["line"])}</b><br>'
                         f'<span style="color:#555">Due {html.escape(_when(i))} · from {html.escape(i["file"])}</span></li>')
        lines.append("")
        parts.append("</ul>")
    lines += [f"Open roost: {PUBLIC_URL}", "",
              "You get this because reminders are on in roost. Turn them off on the page."]
    parts.append(f'<p><a href="{html.escape(PUBLIC_URL)}">Open roost</a></p>'
                 '<p style="color:#777;font-size:13px">You get this because reminders are on in roost. '
                 "Turn them off on the page.</p></div>")
    return subject, "\n".join(lines), "".join(parts)


def items_for(uid, today):
    return [i for i in userspace.due(uid, today, WINDOW_DAYS) if i["days"] <= WINDOW_DAYS]


def send_for(uid, send, today=None, force=False):
    """Email one user their digest. Returns 'sent', 'nothing due', 'already sent today' or 'off'."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    user = accounts.get_user(uid)
    if not force and not user.get("reminders"):
        return "off"
    if not force and user.get("last_digest") == today.isoformat():
        return "already sent today"
    items = items_for(uid, today)
    if not items:
        return "nothing due"
    subject, text, body = compose(items)
    send(user["email"], subject, text, body, kind="test" if user.get("test") else "user")
    if not force:
        accounts.update_user(uid, last_digest=today.isoformat())
    return "sent"


def run(send, today=None):
    """Send every user with reminders on their digest; one per user per day."""
    results = {}
    for uid, user in accounts.users().items():
        if user.get("test"):
            continue
        try:
            results[uid] = send_for(uid, send, today)
        except Exception as e:  # one user's failure doesn't stop the rest
            results[uid] = f"failed: {type(e).__name__}"
    return results
