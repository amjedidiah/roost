# AGENTS.md

This file provides guidance to coding agents (Claude Code and others) when working with code in this repository.

## Status

Greenfield. The repo currently contains only `development_plan.md` (the source of truth for scope, phases and checklist) — no code yet (git repo initialized on `main`). Update this file once real build/run/test commands exist; don't invent them before then.

## What roost is

Hacksgiving 2026 (Fly.io) entry: a personal **archivist agent** running as a Python HTTP service on a Fly.io **Sprite** (persistent Firecracker microVM). It ingests the user's own Box documents into Pinecone vector memory (the "nest"), and answers questions by retrieving context and returning a **typed, schema'd decision**. TypeSafe AI (Jev) and Gemini were both dropped from scope on Nov 25 2026; don't reintroduce them or add another model connector.

Deadline: midnight PST Sun Nov 29 2026 (08:00 WAT Mon Nov 30). Sprite + connectors must stay live through Dec 1 (judging).

## Architecture (planned)

Single service, two endpoints:

- `POST /ingest` — Box connector → list files, fetch text for supported types → upsert into Pinecone index `roost` using **Pinecone hosted embeddings** (`llama-text-embed-v2`, text in field `chunk_text`), one namespace. Source docs are in Box folder `roost/`; skip types stdlib can't read. A cursor in `nest.json` on the persistent filesystem makes re-ingest incremental; running it twice must add nothing the second time.
- `GET /ask?q=...` — Pinecone top-k query → typed decision from `q` + context with a fixed output schema, e.g. `{ answered: bool, source_file: str, category: enum, priority: enum, next_action: enum }` → return the JSON plus a one-line template rendered from the typed fields. The engine *decides*; a template phrases it — no free-form prose generation. Each answer is appended under `history/`.

**Decision engine:** a rules template, no model. It fills the schema from the retrieved matches (scores, metadata, keywords).

## Hard constraints

- **Python stdlib only** (`http.server`, `urllib`, `json`). No framework, no third-party deps, no DB beyond Pinecone, no auth UI, single user.
- **No credentials on the Sprite.** `.env` (gitignored) holds `PINECONE_API_KEY` for local use only — never copy it to the Sprite, and never read it from code that runs there. On the Sprite, all partner calls go through the Sprites connector gateway with **no auth header**:
  `https://api.sprites.dev/v1/gateway/<provider>/<conn_id>/<path>`
  Discover connection IDs at runtime via `GET https://api.sprites.dev/v1/gateway/list` (returns `gateway_base_url` + `usage_snippet`) — don't hardcode them.
- **RAM does not survive hibernation; the filesystem does.** All state (cursor, history) goes to disk, not module globals.
- **Triggered, not scheduled.** Sprites have no native cron; wake is by HTTP request. Don't build an in-process scheduler.
- **$0 to build and run** — free tiers only (Fly Free, Box personal, Pinecone Starter).
- **Written fresh this week.** All code is new for Hacksgiving; keep the commit history within Nov 23–29.

## Sprite commands (from the plan)

```sh
curl -fsSL https://sprites.dev/install.sh | sh && sprite login
sprite create --skip-console --label env=hacksgiving roost && sprite use roost   # URL: https://roost-b6xbd.sprites.app
sprite file push -p service.py /home/sprite/roost/service.py                      # deploy (Sprite user is `sprite`, not root)
sprite exec --no-stdin -- sprite-env services create roost --cmd python3 \
  --args /home/sprite/roost/service.py --dir /home/sprite/roost --http-port 8080
sprite exec --no-stdin -- sprite-env services restart roost                       # after pushing new code
sprite config update --url-auth public                                            # public URL
sprite exec --no-stdin -- curl -s https://api.sprites.dev/v1/gateway/list        # verify connectors
sprite checkpoint create --comment "MVP working"
```

Connectors (Box, Pinecone) are granted in the Fly dashboard to the label `env=hacksgiving`; they are default-deny. The Pinecone connector can't create indexes (403); do that in the Pinecone console.
