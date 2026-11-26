# AGENTS.md

This file provides guidance to coding agents (Claude Code and others) when working with code in this repository.

## Status

`development_plan.md` is the source of truth for scope, phases and checklist. The multi-user product ("never miss what's due", Phase 6) is live at https://roost-b6xbd.sprites.app. What remains is Phase 5: the demo video, the social post and the submission form.

## Commands

```sh
python3 -m unittest discover -s tests -t .                       # all tests (local; fakes, no network)
python3 -m unittest tests.test_multiuser.InboxTest               # one class
./scripts/deploy.sh                                              # push code, samples and the page to the Sprite, restart
./scripts/deploy.sh api                                          # same, but leave the live page (web/index.html) alone
./scripts/smoke.sh                                               # live pass on the Sprite that deletes its own account (once per code version; --force)
python3 scripts/preview.py                                       # the local page against the live API: http://localhost:8765
./scripts/set-token.sh                                           # create ROOST_TOKEN in .env (if missing), install its hash on the Sprite
./scripts/create-index.sh                                        # one-time: create the roost-nest index with the .env key
```

The gateway only works from inside the Sprite, so anything that touches Box, Pinecone or AgentMail must run there (`sprite exec --no-stdin -- sh -c 'cd /home/sprite/roost && python3 ...'`). Local Python is 3.9; the Sprite has 3.13, so keep code 3.9-compatible. `pdftotext` (poppler-utils) is installed on the Sprite but not locally, so PDF support only shows up there.

**Before deploying the page:** the owner must see and approve a local preview (`scripts/preview.py`, or screenshots from a local server with the fakes) first. Server-only changes go out with `deploy.sh api`.

## What roost is

Hacksgiving 2026 (Fly.io) entry: **never miss what your documents say is due.** People sign in with their email (6-digit code or link, no passwords), add documents (upload PDF/Word/Markdown/text, the 8 samples, or forward an email to `roost-nest@agentmail.to`), and get a "Coming up" list of every dated to-do across them plus a morning reminder email. Asking questions about your documents is a secondary feature. All on a Fly.io **Sprite**, with **Box** (files), **Pinecone** (vectors) and **AgentMail** (email) reached only through Sprites connectors.

TypeSafe AI, Gemini and Ollama were dropped from scope on Nov 25 2026; don't add a model connector. The rules are fixed and inspectable.

Deadline: midnight PST Sun Nov 29 2026 (08:00 WAT Mon Nov 30). Sprite + connectors must stay live through Dec 1 (judging).

## Architecture

One stdlib HTTP service (`service.py`) on port 8080, run as the Sprite service `roost`.

- **Routes.** Page: `GET /`, `/assets/*`, `/healthz`. Sign-in: `POST /api/auth/start|verify|signout`, `GET /auth?t=`. Signed in (cookie `roost_session`): `GET /api/me|documents|due|ask`, `POST /api/upload|samples|documents/<id>/delete|sync|settings|digest/test|account/delete`. Owner (`X-Roost-Token`): `POST /internal/sync-all|digest|delete-user`.
- **Security.** Every `POST /api/*` needs `X-Requested-With: roost` (CSRF). Sessions are `HttpOnly; Secure; SameSite=Lax`, 30 days. Sign-in tokens, codes and session ids are stored only as SHA-256. The owner token lives only in the local `.env` and the GitHub secret; the Sprite keeps its hash in `data/token.sha256` and fails closed (503) without it. The page has a strict CSP (`default-src 'none'`, self only); render document and email text with `textContent`, never `innerHTML`.
- **Accounts** (`accounts.py`): `data/accounts.json`, `signin.json`, `sessions.json`. Limits: 40 users, 3 sign-in emails per address per hour, 20 overall, 5 code attempts, 15-minute codes. A sign-in request carrying the owner token is a **test** sign-in: it skips and doesn't count towards those limits, and the account is marked `test` (no daily digest). `delete_user` drops the account and its sessions and voids pending sign-ins.
- **Per user** (`userspace.py`): Box folder `roost/users/<uid>/`, Pinecone namespace `u-<uid>`, state `data/users/<uid>/nest.json` (per file: Box sha1, name, chunk count, size, due items) and `history/`. Limits: 10 files, 10 MB, 5 MB per file; types from `extract.supported_extensions()`. `erase` empties every Box file, clears the namespace, removes the state and the account.
- **Ingest** (`ingest.py`, `extract.py`): md/markdown/txt as is, docx via zipfile + XML, pdf via `pdftotext -layout`. Heading-prefixed chunks (≤1200 chars), embedded with the connector's `/embed` (`llama-text-embed-v2`, 1024 dims), upserted as plain vectors to index **`roost-nest`** with the chunk text in metadata. Vector ids are `<box_file_id>#<chunk_index>`. Unchanged files (same sha1 and name, with due items recorded) are skipped; empty files are skipped (that's how removal works).
- **Due** (`due.py`): `extract_items` rejoins hand-wrapped lines (`_continues`: only when the previous line stops without punctuation and the next starts lower-case/with a digit or the previous ends on a lower-case word; so PDF lines stay apart), splits non-to-do lines into sentences, keeps text that has a date **and** a deadline word, one item per first date per file (to-do beats line, longer beats shorter). `upcoming` picks each item's next date, keeps overdue items 14 days, and classifies urgency (≤7 high, ≤30 medium) and next step.
- **Mail** (`mail.py`, `digest.py`, `inbox.py`): sending through AgentMail with daily budgets per kind (`user` 88, `test` 10) in `data/mail_log.json`. The digest is one email per user per day when something is due within 7 days. `inbox.poll` turns email from a known sender into a `.txt` document (text only; HTML-only mail is converted); processed ids in `data/inbox.json`. Roost's own mail to itself is ignored unless the subject starts with `roost-smoke:`.
- **Questions** (`ask.py`, `decide.py`): embed, query top 8 in the user's namespace, and at ≥ 0.28 read the whole best file back and run the pure rules engine (`decide()` takes `today`): file, category, the best-matching to-do (ties to the most urgent), its own date, priority, next action, a template summary.
- **Schedule:** `.github/workflows/daily.yml` at 06:00 UTC calls `/internal/sync-all` (forwarded mail, then every user's Box folder) and `/internal/digest`. Logs are public, so it prints counts only.
- **Seams for tests:** `service.make_box`, `make_nest`, `send_mail`, `make_inbox`; fakes in `tests/fakes.py`.

Design decisions live in `PRODUCT.md`, `DESIGN.md` and `.impeccable/surfaces/web-index-html.md` (dark "Night Shelf"): yellow `#ffd60a` marks only the next thing to do, urgency is a square mark plus a word, 44px touch targets, destructive actions confirm inline and move focus, no tabular figures (Schibsted's `tnum` widens `.` and `,`).

## Connector limits (checked Nov 2026)

- **Box:** list, download, folder create (409 returns the existing id), upload (same name = new version), replace content work. **Rename and delete are not forwarded** (403), so removing a file empties it.
- **Pinecone:** forwards `/embed` and the vectors API (`upsert`, `delete` incl. `deleteAll`, `fetch`, `query`, `describe_index_stats`) with `X-Pinecone-API-Version: 2025-04`. **Not** index creation or the 2026-07 documents API. Console-made indexes get a document schema that rejects vector reads; `roost-nest` was created from the laptop with the `.env` key.
- **AgentMail:** send, list messages, get message, get thread work. **Attachment endpoints are not forwarded** ("endpoint is not supported by the AgentMail connector"). Message ids must be URL-encoded except `@`. The key is scoped to the `roost-nest@agentmail.to` inbox.
- **Gateway:** occasional 503s; `gateway.request` retries GETs twice.

## Hard constraints

- **Python stdlib only.** No framework, no third-party deps, no DB beyond Pinecone and JSON files on the Sprite.
- **No credentials on the Sprite.** `.env` (gitignored) holds `PINECONE_API_KEY`, `AGENTMAIL_API_KEY` and `ROOST_TOKEN` for local use only; never copy them to the Sprite or print them. `smoke.sh` passes the token over stdin for one run. On the Sprite, all partner calls go through `https://api.sprites.dev/v1/gateway/<provider>/<conn_id>/<path>` with **no auth header**; discover connection ids at runtime via `GET https://api.sprites.dev/v1/gateway/list`.
- **State on disk, not in RAM.** RAM caches are fine; everything that matters is a JSON file in `data/` (atomic writes via `store.write_json`).
- **No in-process scheduler.** Sprites have no cron; the daily run is GitHub Actions.
- **$0 to build and run:** free tiers only (Fly, Box personal, Pinecone Starter, AgentMail 100 emails/day).
- **Tests never spend real users' limits:** use fakes locally; live checks go through `smoke.sh` (test sign-in, test email budget, deletes its account).
- **Written fresh this week.** Keep the commit history within Nov 23–29; no AI attribution in commits.

## Sprite commands

```sh
sprite create --skip-console --label env=hacksgiving roost && sprite use roost   # URL: https://roost-b6xbd.sprites.app
sprite exec --no-stdin -- sprite-env services create roost --cmd python3 \
  --args /home/sprite/roost/service.py --dir /home/sprite/roost --http-port 8080
sprite exec --no-stdin -- sprite-env services restart roost
sprite config update --url-auth public
sprite exec --no-stdin -- curl -s https://api.sprites.dev/v1/gateway/list        # verify connectors
sprite checkpoint create --comment "..."                                          # snapshot before risky changes
```

Connectors (Box, Pinecone, AgentMail) are granted in the Fly dashboard to the label `env=hacksgiving`; they are default-deny.

## After judging (Dec 1 2026)

All user data must be deleted after judging (the page promises it):
1. `POST /internal/delete-user` with `{"all": true}` and the `X-Roost-Token` header: empties every user's Box files, clears their Pinecone namespaces, removes their state and accounts.
2. **Then delete the `roost/users` folder in the Box web app.** The connector can't delete or rename, so step 1 leaves empty files (with their original names) and the per-user folders, including `roost/users/_probe`.
