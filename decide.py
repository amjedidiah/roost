"""The typed decision: fixed rules over retrieved chunks, no model.

Given the question, the vector matches and the full text of the best-matching
file, fill a fixed schema: whether the nest answers it, which file, what kind of
document, how urgent, and what to do next. Every value comes from the user's own
documents; the summary line is a template over those fields.
"""

import datetime as dt
import os
import re

ANSWER_THRESHOLD = float(os.environ.get("ROOST_ANSWER_THRESHOLD", "0.28"))

CATEGORIES = ("home", "finance", "health", "travel", "purchases", "personal", "work", "other")
PRIORITIES = ("high", "medium", "low")
NEXT_ACTIONS = ("act_now", "follow_up", "schedule", "review", "none")

CATEGORY_WORDS = {
    "home": ["lease", "rent", "landlord", "tenancy", "tenant", "apartment", "deposit", "maintenance",
             "move-out", "utilities"],
    "finance": ["tax", "taxes", "insurance", "premium", "receipt", "receipts", "deduction", "deductions",
                "invoice", "bill", "budget", "accountant", "policy", "excess", "deductible"],
    "health": ["dentist", "dental", "doctor", "clinic", "health", "medical", "prescription", "filling",
               "check-up", "x-rays"],
    "travel": ["trip", "flight", "flights", "itinerary", "passport", "guesthouse", "hotel", "travel",
               "check-in", "airport"],
    "purchases": ["warranty", "purchase", "purchased", "order", "retailer", "device", "laptop", "serial",
                  "repair"],
    "personal": ["recipe", "bake", "baking", "dough", "flour", "starter", "oven", "hobby", "ingredients"],
    "work": ["project", "projects", "hackathon", "career", "client", "effort", "blocker", "build", "built"],
}

URGENT = re.compile(r"\b(this week|asap|urgent(ly)?|today|immediately|right away)\b", re.I)
FOLLOW_UP = re.compile(r"^(chase|follow up|call|confirm|request|check|email|ask|update)\b", re.I)
ACTION_HEADING = re.compile(r"\b(to ?do|next steps?|follow-?ups?|actions?)\b", re.I)
BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*)$")
WORD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
STOPWORDS = set(
    "a an and are at be by can do does for from have how i in is it me my of on or should so the "
    "to was what when where which who will with you your am did need any still much many before after "
    "about out up get there anything something things sort make".split()
)
URGENT_DAYS = 7  # an undated "this week" item ranks like one due in a week

MONTHS = {m: i for i, names in enumerate(
    [("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",),
     ("jun", "june"), ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"),
     ("oct", "october"), ("nov", "november"), ("dec", "december")], start=1) for m in names}
_MONTH = r"(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?"
# Spaces and tabs only: \s would join "28 December" to a "1." list item on the next line.
_DAY_MONTH = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?[ \t]+" + _MONTH + r"(?:,?[ \t]+(\d{4}))?\b", re.I)
_MONTH_DAY = re.compile(r"\b" + _MONTH + r"[ \t]+(\d{1,2})(?:st|nd|rd|th)?(?:,?[ \t]+(\d{4}))?\b", re.I)
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


# --- extraction ----------------------------------------------------------------

def find_dates(text, today):
    """All calendar dates mentioned in text. A date without a year is taken to be
    in today's year, or next year if that would put it more than 6 months ago."""
    found = []

    def add(year, month, day):
        try:
            if year:
                found.append(dt.date(int(year), month, int(day)))
                return
            d = dt.date(today.year, month, int(day))
            if (today - d).days > 183:
                d = d.replace(year=today.year + 1)
            found.append(d)
        except ValueError:
            pass  # 31 February and friends

    for day, month, year in _DAY_MONTH.findall(text):
        add(year, MONTHS[month.lower()], day)
    # Blank out day-month dates so "28 December 2026" can't also read as "December 20...".
    for month, day, year in _MONTH_DAY.findall(_DAY_MONTH.sub(lambda m: " " * len(m.group(0)), text)):
        add(year, MONTHS[month.lower()], day)
    for year, month, day in _ISO.findall(text):
        add(year, int(month), day)
    return found


def next_date(text, today):
    upcoming = [d for d in find_dates(text, today) if d >= today]
    return min(upcoming) if upcoming else None


def action_items(chunks):
    """Bullet lines that sit under a 'To do' / 'Next step' / 'Follow-ups' heading.
    Chunks start with their heading line (see ingest.chunk_text)."""
    items = []
    for chunk in chunks:
        heading, _, body = chunk.partition("\n")
        if not ACTION_HEADING.search(heading):
            continue
        for line in body.splitlines():
            match = BULLET.match(line)
            if match:
                items.append(match.group(1).strip())
    return items


def _words(text):
    return {w for w in WORD.findall(text.lower()) if w not in STOPWORDS}


def _urgency_days(item, today):
    """Days until the item is due: its own date, a week if it says 'this week' etc., else None."""
    due = next_date(item, today)
    if due:
        return (due - today).days
    return URGENT_DAYS if URGENT.search(item) else None


def pick_action(question, items, today):
    """The to-do most related to the question; ties go to the most urgent, then bolded, then first."""
    q = _words(question)

    def score(indexed):
        index, item = indexed
        days = _urgency_days(item, today)
        return (len(q & _words(item)), days is not None, -(days if days is not None else 0),
                "**" in item, -index)

    if not items:
        return None
    _, best = max(enumerate(items), key=score)
    return best


def categorise(file_name, text):
    words = WORD.findall(f"{file_name} {text}".lower())
    counts = {c: sum(words.count(k) for k in keys) for c, keys in CATEGORY_WORDS.items()}
    best = max(CATEGORIES[:-1], key=lambda c: counts[c])  # ties go to the earlier category
    return best if counts[best] else "other"


def _plain(text):
    return re.sub(r"\*\*|__|`", "", text).strip()


def _fmt(d):
    return f"{d.day} {d.strftime('%b %Y')}"


# --- decision ------------------------------------------------------------------

def decide(question, matches, doc_chunks, today):
    """matches: Pinecone matches ({score, metadata}) best first. doc_chunks: the
    full chunk texts of the best-matching file, in order (may be empty)."""
    top = matches[0] if matches else None
    confidence = round(top["score"], 3) if top else 0.0
    listed = [{"file": m["metadata"].get("file_name"), "chunk": int(m["metadata"].get("chunk_index", 0)),
               "score": round(m["score"], 3)} for m in matches[:5]]

    if not top or top["score"] < ANSWER_THRESHOLD:
        return {
            "question": question, "answered": False, "source_file": None, "category": "other",
            "priority": "low", "next_action": "none", "due": None, "action_item": None,
            "confidence": confidence, "evidence": None, "matches": listed,
            "summary": f"Nothing in the nest matches this closely enough (best score {confidence}).",
        }

    meta = top["metadata"]
    source = meta.get("file_name")
    chunks = doc_chunks or [m["metadata"].get("chunk_text", "") for m in matches
                            if m["metadata"].get("file_id") == meta.get("file_id")]
    text = "\n\n".join(chunks)

    raw_item = pick_action(question, action_items(chunks), today)
    item = _plain(raw_item) if raw_item else None
    # With a to-do, only its own date counts; another date in the file would mislabel it.
    due = next_date(raw_item, today) if raw_item else next_date(text, today)

    if due is not None:
        days = (due - today).days
        priority = "high" if days <= 7 else "medium" if days <= 30 else "low"
    elif item and URGENT.search(item):
        priority = "high"
    else:
        priority = "medium" if item else "low"

    if not item:
        next_action = "review"
    elif priority == "high":
        next_action = "act_now"
    elif FOLLOW_UP.match(item):
        next_action = "follow_up"
    else:
        next_action = "schedule"

    category = categorise(source or "", text)
    if item:
        summary = f"{source} answers this. {category.title()}, {priority} priority: {item}"
        if due:
            summary += f" (due {_fmt(due)})"
    else:
        summary = f"{source} answers this ({category}). No open action; see the evidence."

    return {
        "question": question, "answered": True, "source_file": source, "category": category,
        "priority": priority, "next_action": next_action, "due": due.isoformat() if due else None,
        "action_item": item, "confidence": confidence,
        "evidence": _plain(meta.get("chunk_text", ""))[:400], "matches": listed, "summary": summary,
    }
