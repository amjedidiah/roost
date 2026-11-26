"""What's due: dated items pulled from a document's own lines.

At ingest, `extract_items` stores each file's dated lines (to-do bullets with a
date, and any other line that has a date and a deadline word). At read time,
`upcoming` turns them into the "Coming up" list for a given day. Every item is
a line copied from the file; nothing is inferred beyond the date.
"""

import re

from decide import ACTION_HEADING, BULLET, FOLLOW_UP, _plain, find_dates

DEADLINE = re.compile(
    r"\b(due|by|before|until|deadline|expires?|expiry|renews?|auto-renews?|pay|payable|book|"
    r"cancel(?:lation)?|notice|ends?|closes?|submit|return|appointment|check-?up|departs?|reserve)\b",
    re.I,
)
OVERDUE_DAYS = 14  # overdue items stay listed this long


def _clean(line):
    line = BULLET.sub(r"\1", line) if BULLET.match(line) else line
    line = line.strip().strip("|").replace("|", " · ")
    return re.sub(r"\s+", " ", _plain(line)).strip(" ·*_")


def _logical_lines(body):
    """Rejoin lines the file wrapped by hand; bullets, table rows and blank lines start new ones."""
    lines = []
    for raw in body.splitlines():
        stripped = raw.strip()
        if not stripped:
            lines.append("")
        elif lines and lines[-1] and not BULLET.match(raw) and not stripped.startswith("|") \
                and not lines[-1].lstrip().startswith("|"):
            lines[-1] += " " + stripped
        else:
            lines.append(raw)
    return [l for l in lines if l.strip() and not set(l.strip()) <= set("|-: ")]


SEGMENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z])|\s+·\s+|;\s+")


def extract_items(chunks, today):
    """Dated lines from a file's chunks: [{"line", "dates": [iso, ...], "kind", "heading"}].

    A to-do bullet (under a To do / Next steps / Follow-ups heading) is kept whole;
    any other line is split into sentences. Either way the text must name a date
    and a deadline word ("due", "by", "before", "expires", ...). One item per
    date per file: a to-do beats a plain line, and a longer line beats a shorter one.
    """
    best = {}
    for chunk in chunks:
        heading, _, body = chunk.partition("\n")
        in_todo = bool(ACTION_HEADING.search(heading))
        candidates = [(heading, False)]
        for line in _logical_lines(body):
            if in_todo and BULLET.match(line):
                candidates.append((line, True))
            else:
                candidates.extend((seg, False) for seg in SEGMENT.split(line))
        for raw, is_todo in candidates:
            if not DEADLINE.search(raw):
                continue
            dates = find_dates(raw, today)
            if not dates:
                continue
            line = _clean(raw)
            if not line:
                continue
            item = {"line": line, "dates": sorted({d.isoformat() for d in dates}),
                    "kind": "todo" if is_todo else "line", "heading": heading.strip()}
            key = item["dates"][0]
            rank = (is_todo, len(line))
            if key not in best or rank > best[key][0]:
                best[key] = (rank, item)
    return [item for _, item in sorted(best.values(), key=lambda x: x[1]["dates"][0])]


def _pick(dates, today):
    """The date that matters today: the next upcoming one, else a recent past one."""
    import datetime as dt
    parsed = [dt.date.fromisoformat(d) for d in dates]
    future = [d for d in parsed if d >= today]
    if future:
        return min(future)
    recent = [d for d in parsed if (today - d).days <= OVERDUE_DAYS]
    return max(recent) if recent else None


def classify(line, due, today):
    days = (due - today).days
    urgency = "high" if days <= 7 else "medium" if days <= 30 else "low"
    if FOLLOW_UP.match(line):
        action = "follow_up"
    elif urgency == "high":
        action = "act_now"
    else:
        action = "schedule"
    return days, urgency, action


def upcoming(files, today, within_days=60):
    """files: {file_id: {"name", "due": [items]}} → soonest-first list of due items."""
    out = []
    for file_id, f in files.items():
        for item in f.get("due", []):
            due = _pick(item["dates"], today)
            if due is None or (due - today).days > within_days:
                continue
            days, urgency, action = classify(item["line"], due, today)
            out.append({"file_id": file_id, "file": f["name"], "line": item["line"], "kind": item["kind"],
                        "due": due.isoformat(), "days": days, "overdue": days < 0,
                        "urgency": urgency, "next_action": action})
    out.sort(key=lambda x: (x["due"], x["kind"] != "todo", x["file"]))
    return out
