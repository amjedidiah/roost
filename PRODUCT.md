# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Python standard library only (`http.server`), no build step and no dependencies, running as a service on a Fly.io Sprite. The web UI is one self-contained HTML file (inline CSS and vanilla JS) served at `GET /`, talking to JSON routes under `/api/` with a session cookie. Box, Pinecone and AgentMail are reached only through the Sprites connector gateway; a GitHub Actions schedule triggers the daily run.

## Users

- **Primary: people with bills, bookings and letters**, including non-technical people, on a phone. They want to stop missing renewals, payments, appointments and notice periods buried in their documents.
- **Judges** (Fly.io Hacksgiving 2026): they try it live (sign in with their own email, press "Try sample documents") or watch the labelled demo video. They give it seconds, not minutes.
- **The owner**: runs the Sprite, deploys, and wipes all data after judging.

## Product Purpose

roost reads your documents and tells you what they say is due. Sign in with your email, add files (or forward an email), and roost lists every dated thing to do across them, soonest first, with the exact line it came from, and emails you the morning something is due within a week. You can also ask a question about your documents and get the file, the to-do and the date back. Success: someone adds their documents once and never misses a renewal, payment or appointment written in them.

## Positioning

Not another chatbot over your files. The dates come from fixed, inspectable rules over your own words, so every item traces to a quoted line and the same document always gives the same list. The Sprite holds no partner credentials: Box, Pinecone and AgentMail are all called through Sprites connectors. No passwords: sign-in is a code sent to your email.

## Operating Context

- Sign in: email → 6-digit code (or link) → signed in for 30 days.
- Add documents: upload (PDF, Word, Markdown, text; 10 files, 10 MB, 5 MB each), the 8 sample documents, or forward an email from the sign-in address to `roost-nest@agentmail.to` (text only; attachments must be uploaded).
- Coming up: grouped Overdue / This week / Later, each with date, line, when, urgency, next step and file.
- Reminders: on by default; one email a day when something is due within 7 days; "Send me one now" (3 a day).
- Ask: about 1–3 seconds; below a 0.28 match it says it found nothing.
- Account: delete removes the account, sessions, vectors and file contents.
- Demo limits: 40 people; everything deleted after 1 December 2026.

## Capabilities and Constraints

- Errors come back as JSON `{ "error": "..." }` with a sentence safe to show; the page shows it as written.
- Email budget: 88 user emails and 10 test emails a day (AgentMail free tier is 100).
- The Box connector can't delete or rename, so removed files are emptied; their names stay until the owner deletes `roost/users` in Box.
- Triggered, not scheduled: the Sprite has no cron; GitHub Actions calls it each morning.

## Brand Commitments

- Name is lowercase **roost**. The bird idea lives only in the name: no birds, nests or twigs as decoration.
- Plain words a non-technical person would use on every control.
- Not a chat interface. Not a busy dashboard. Minimal and dark (approved Nov 25).

## Evidence on Hand

- Eight fictional sample documents in `sample-docs/` (lease, car insurance, dentist, Lisbon trip, tax receipts, laptop warranty, sourdough recipe, side projects). Their companies, names and booking references are invented.
- The live service and its smoke test (`scripts/smoke.sh`, 15 checks).
- No users, testimonials, metrics or customers exist. Do not invent any.

## Product Principles

1. Dates first: the page leads with what is due, not with features.
2. Every item is traceable to a line in a named file.
3. Be honest: say when nothing was found, when an attachment can't be read, when a limit is hit.
4. Quiet by default; the content is the user's own documents.
5. The user stays in control: remove any document, turn reminders off, delete the account.
