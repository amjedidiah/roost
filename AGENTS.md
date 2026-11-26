# AGENTS.md

This file provides guidance to coding agents (Claude Code and others) when working with code in this repository.

## Status

`development_plan.md` is the source of truth for scope, phases and checklist. Phases 0–4 are done; Phase 5 (demo and submission) is next.

## Commands

```sh
python3 -m unittest discover -s tests -t .                       # all tests (local; fakes, no network)
python3 -m unittest tests.test_ingest.IngestTest.test_second_run_is_a_no_op   # one test
./scripts/deploy.sh                                              # push *.py to the Sprite and restart the service
./scripts/create-index.sh                                        # one-time: create the roost-nest index with the .env key
./scripts/set-token.sh                                           # create ROOST_TOKEN in .env (if missing), install its hash on the Sprite
./scripts/smoke.sh                                               # live pass on the Sprite that deletes its own account (once per code version; --force)
curl -X POST -H "X-Roost-Token: $ROOST_TOKEN" https://roost-b6xbd.sprites.app/ingest   # run ingest
curl -G -H "X-Roost-Token: $ROOST_TOKEN" --data-urlencode "q=when does my car insurance renew" https://roost-b6xbd.sprites.app/ask
```

**Auth:** `/ingest`, `/ask` and `/nest` require the `X-Roost-Token` header. The token lives only in the local `.env`; the Sprite keeps just its SHA-256 in `data/token.sha256` and fails closed (503) without it. `/`, `/healthz` and `/assets/*` are open.

The gateway only works from inside the Sprite, so anything that touches Box or Pinecone must run there (`sprite exec --no-stdin -- sh -c 'cd /home/sprite/roost && python3 ...'`). Local Python is 3.9; the Sprite has 3.13, so keep code 3.9-compatible.

## What roost is

Hacksgiving 2026 (Fly.io) entry: a personal **archivist agent** running as a Python HTTP service on a Fly.io **Sprite** (persistent Firecracker microVM). It ingests the user's own Box documents into Pinecone vector memory (the "nest"), and answers questions by retrieving context and returning a **typed, schema'd decision**. TypeSafe AI (Jev) and Gemini were both dropped from scope on Nov 25 2026; don't reintroduce them or add another model connector.

Deadline: midnight PST Sun Nov 29 2026 (08:00 WAT Mon Nov 30). Sprite + connectors must stay live through Dec 1 (judging).

## Architecture (planned)

Single service, two endpoints:

Web UI: `web/index.html` is one self-contained page (inline CSS + vanilla JS, no build) served at `GET /` with a strict CSP (`default-src 'none'`, self only); font in `web/assets/`. It calls `GET /ask`, `POST /ingest` and `GET /nest` (token-protected, read-only list of files from `nest.json`). Render document text with `textContent` only, never `innerHTML`. Design decisions live in `PRODUCT.md`, `DESIGN.md` and `.impeccable/surfaces/web-index-html.md` (Swiss Data Sheet direction): yellow `#ffd60a` is reserved for the action line, priority is shown by the square mark's form, and tabular figures apply only to dates (in Schibsted they also widen `.` and `,`).

Modules: `auth.py` (shared-secret check), `gateway.py` (connection discovery + keyless HTTP), `box.py`, `nest.py` (Pinecone), `ingest.py` (chunking + sync logic), `decide.py` (rules engine, pure), `ask.py` (search + decide + history), `service.py` (HTTP).

- `POST /ingest` — lists Box folder `roost/`, downloads `.md`/`.markdown`/`.txt` files, splits them into heading-prefixed chunks (≤1200 chars), embeds them through the connector's `/embed` (`llama-text-embed-v2`, 1024 dims), and upserts plain vectors to Pinecone index **`roost-nest`**, namespace `me`. Vector ids are `<box_file_id>#<chunk_index>`; metadata holds `file_id`, `file_name`, `chunk_index`, `chunk_text`, `modified_at`. `data/nest.json` (on the Sprite, gitignored) records each file's Box `sha1`, name and chunk count: unchanged files are skipped, changed files are re-embedded and their surplus chunk ids deleted, and files gone from Box have all their chunks deleted. A lock returns 409 if an ingest is already running.
- `GET /ask?q=...` — embeds `q` (`input_type: query`), queries top 8, and if the best score is ≥ `ROOST_ANSWER_THRESHOLD` (0.28) fetches every chunk of that file (count from `nest.json`) so dates and to-dos outside the matched chunks count. `decide.py` then fills the schema; the result is appended to `data/history/YYYY-MM-DD.jsonl`.

**Decision engine (`decide.py`):** fixed rules, no model; `decide()` is pure and takes `today`. `answered` = score threshold. `category` = keyword counts over file name + text (enum in `CATEGORIES`). `action_item` = the bullet under a To do / Next steps / Follow-ups heading with the most question-word overlap; ties go to the most urgent (own date, or "this week"/"asap" ≈ 7 days), then bolded. `due` = the action item's own date only (another date in the file would mislabel it), or the file's next date when there is no action item. `priority` = ≤7 days high, ≤30 medium, else low; undated urgent wording → high. `next_action` = none / review / act_now (high) / follow_up (chase, call, confirm…) / schedule. Date parsing only matches within one line (`[ \t]`, not `\s`) so a heading date can't join a numbered list item. `summary` is a template over these fields.

## After judging (Dec 1 2026)

All user data must be deleted after judging (the page promises it):
1. `POST /internal/delete-user` with `{"all": true}` and the `X-Roost-Token` header: empties every user's Box files, clears their Pinecone namespaces, removes their state and accounts.
2. **Then delete the `roost/users` folder in the Box web app.** The connector can't delete or rename, so step 1 leaves empty files (with their original names) and the per-user folders, including `roost/users/_probe`.

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

Connectors (Box, Pinecone) are granted in the Fly dashboard to the label `env=hacksgiving`; they are default-deny.

**Pinecone connector limits:** it forwards `/embed` and the vectors API (`/indexes/<name>/vectors/upsert`, `/vectors/delete`, `/query`, `/describe_index_stats`) with `X-Pinecone-API-Version: 2025-04`. It does **not** forward index creation or the 2026-07 documents API (`/namespaces/.../documents/*`). Indexes made in the Pinecone console get a document schema, which rejects vector reads, so don't use them. `roost-nest` was created from the laptop via `POST https://api.pinecone.io/indexes` (API 2025-04) with the `.env` key. The old `roost` index is unused.
