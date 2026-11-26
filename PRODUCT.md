# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Python standard library only (`http.server`), no build step and no dependencies. The web UI is one self-contained HTML file (inline CSS and vanilla JS) served by `service.py` at `GET /`, talking to the existing JSON endpoints `GET /ask?q=` and `POST /ingest`.

## Users

- **Primary: hackathon judges** (Fly.io Hacksgiving 2026). They meet roost through a recorded Playwright demo video with labels, and some may try the live page with a token we hand them. They give it seconds, not minutes.
- **Secondary: the owner**, asking questions about their own documents from a phone. roost began as "a service I can hit from my phone".

## Product Purpose

roost is a personal archivist that runs on a Fly.io Sprite. It loads the owner's own documents from a Box folder into Pinecone vector memory (the "nest"). Asked a question, it returns a **typed decision**, not prose: which file answers it, category, priority, next action, due date, the exact to-do line from the document, and the evidence passage. Success for the page: a judge understands "your documents in, typed decision out" within one viewport, and sees an answer happen.

## Positioning

The decision is made by fixed, inspectable rules over the user's own documents, with no language model. Every field traces back to a line in a real file, the same question always gets the same answer, and no document text leaves Box and Pinecone. The Sprite holds no partner credentials; every Box and Pinecone call goes through the Sprites connector gateway.

## Operating Context

- Ask flow: type or pick a question, get the decision card in about 1–3 seconds.
- Ingest flow: a manual "re-ingest" that syncs the Box `roost/` folder; first full run about 30 s, re-runs about 1–2 s and usually report "8 unchanged".
- Access: `/ask` and `/ingest` need an `X-Roost-Token` header. The page stores the pasted token in the browser and sends it; without it, both return 401 (missing) or 403 (wrong).
- Not answered: when nothing in the nest scores ≥ 0.28 the response has `answered: false` and a low confidence, which the page must present honestly.

## Capabilities and Constraints

- Decision schema (enums): `category` ∈ home, finance, health, travel, purchases, personal, work, other; `priority` ∈ high, medium, low; `next_action` ∈ act_now, follow_up, schedule, review, none. Also `due` (ISO date or null), `action_item` (string or null), `confidence` (0–1), `evidence` (≤400 chars), `matches` (top 5 file/chunk/score), `summary` (template sentence).
- Ingest response: `added`, `updated`, `unchanged` (count), `removed`, `skipped` (name + reason), `chunks_upserted`, `chunks_deleted`, `files_in_nest`. 409 if an ingest is already running.
- Supported document types: `.md`, `.markdown`, `.txt`.
- Triggered, not scheduled: nothing runs unless asked.
- Error responses are JSON `{ "error": ... }` with 400 / 401 / 403 / 404 / 409 / 502 / 503.

## Brand Commitments

- Name is lowercase **roost**. The idea is a bird returning to its roost; the Pinecone store is "the nest". The metaphor must stay subtle: no literal birds, nests or twigs as decoration.
- Not a chat interface. Not a busy dashboard. Minimal.

## Evidence on Hand

- Eight fictional sample documents in `sample-docs/` (lease, car insurance, dentist, Lisbon trip, tax receipts, laptop warranty, sourdough recipe, side projects). Their companies, names and booking references are all invented; anything shown from them is demo data.
- Real live responses from the deployed service (see README for an example).
- No users, testimonials, metrics or customers exist. Do not invent any.

## Product Principles

1. Show the decision, not a conversation: fields first, prose last.
2. Every claim is traceable: show where an answer came from (file and passage).
3. Be honest about "not answered" and about errors.
4. Quiet by default; the content is the user's own documents.
