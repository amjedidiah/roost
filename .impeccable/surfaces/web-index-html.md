---
version: 2
slug: "web-index-html"
primary_target: "web/index.html"
related_targets: []
---

## Scope

`GET /` of the roost service: the whole product in one page, signed out and signed in. Mode: **Operate**. Phone first (390px), recorded on desktop for the demo.

## Audience and task

Anyone who has bills, bookings and letters, including non-technical people; hackathon judges try it live or watch the labelled demo. Tasks: sign in with an email code, add documents (upload, samples, or forward an email), see what is due, turn reminders on, ask a question, delete the account. States: signed out, code sent, signing in, link expired, roost full, empty (no documents / nothing due), loading, upload limits, errors, reminders on/off, confirm remove, confirm delete account.

## Direction contract

THESIS: one dark column of plain-language sections, with the next thing to do marked in yellow; refuses the chat thread, the busy dashboard and the cute bird theme.
OWN-WORLD: night #111 ground, #1b1b1b cards, #262626 inner surfaces, #f4f4f2 text, #a6a6a6 secondary, Schibsted Grotesk (self-hosted, OFL) in two weights, soft corners on a fixed scale, square urgency marks (filled / half / open) with words, yellow #ffd60a only on the next line, soft red #ff8a7a for lateness and destructive actions.
STORY: "Never miss what your documents say is due": documents in, every date found, a morning email before each one.
FIRST VIEWPORT (signed out): mark, display headline, lede, three numbered steps, then the sign-in card. (Signed in): Coming up first, grouped Overdue / This week / Later.
FINISH: audited Nov 26 (axe 0 violations signed out and in, desktop and phone; 44px targets; inline confirms move focus).

## Unresolved

- Forwarded email: only the text is read; attachments need uploading (connector limit).
