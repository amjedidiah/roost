---
version: 1
slug: "web-index-html"
primary_target: "web/index.html"
related_targets: []
---

## Scope

`GET /` of the roost service: the single page for asking questions and re-ingesting. Mode: **Operate**. Phone first (390px), recorded on desktop too.

## Audience and task

Hackathon judges, mostly through a labelled Playwright video, sometimes live with a token; then the owner on a phone. Task: paste token once, ask or tap a sample question, read the typed decision, optionally re-ingest. States: no token, loading, answered, not answered, error (401/403/409/502/503), ingest running and done.

## Direction contract

THESIS: each answer is set as a numbered data sheet; refuses the chat thread and the rounded-card dashboard.
OWN-WORLD: white sheet, #121212 ink, #6b6b6b secondary, 1px black rules, Schibsted Grotesk (self-hosted, OFL) in two weights with tabular figures on dates, square priority marks (filled / half / open), highlighter yellow #ffd60a only behind the action line; focus is a black outline.
STORY: judges see a question become six typed fields traced to one quoted line from a real file.
FIRST VIEWPORT: lowercase roost mark and nest status top; a large ruled question field; the sheet directly below with rows 1–6, the action line highlighted and captioned with the list it was quoted from; sample questions follow (unnumbered: the order carries no meaning).
FORM: Swiss Data Sheet, position 6 of my ordered list, seed 1913b63f. Signature: rows set in sequence, then the highlighter sweeps the action line.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Raises kept from declined challengers

- Emission-line rail: priority as mark form, never hue alone.
- Orienteering map: the one signal colour reserved for the action line.
- Cassette j-card: relative due ("in 15 days") and scores right-aligned. Tabular figures only on dates: Schibsted's tnum also widens `.` and `,`, so scores stay proportional.
- Midnight transit: only the winning source at full ink; other matches a value step down.

## Unresolved

- No nest-count endpoint exists; status comes from the last ingest response this session.
