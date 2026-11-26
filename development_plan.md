# Development Plan — roost

**Hacksgiving 2026 (Fly.io) entry. Built fresh Nov 23–29, 2026. Target cost: $0 to build and run.**

roost is a personal **archivist agent** that lives on a Fly.io **Sprite** — a hardware-isolated,
persistent Linux microVM. It pulls *your own* documents from **Box**, remembers them as vector
memory in **Pinecone** (the "nest"), and when you ask a question it retrieves the relevant context
and makes a *typed, structured decision* about it — which file answers you, how to categorise it,
what to do next. Two partner connectors, each doing real work; the Sprite never holds a single
credential.

> Theme: a bird returns to its roost. The Sprite is the nest — durable when you want, disposable when
> you don't. The nest (Pinecone) is what makes roost *personal*: it only ever reasons over your stuff.

**Deadline:** midnight PST Sun Nov 29 = **08:00 WAT Mon Nov 30**. Winners emailed Dec 1.

> **Nov 25:** TypeSafe AI (Jev) dropped from scope. Gemini also ruled out (free tier not guaranteed,
> and free-tier prompts may be used by Google). The typed decision is made by a **rules template**.

> **Nov 25, later: direction change to "never miss what's due".** Asking questions about documents is
> where ChatGPT, Claude and Codex are strongest, so roost stops competing there. What a chat assistant
> structurally doesn't do is watch your folder and tell you *before* something is due. roost's main job
> becomes: read every document in the Box folder, list every dated to-do across all of them ("Coming up"),
> and send a daily email of what is due soon, without being asked. Asking a question stays as a secondary
> feature. Fixed rules are a strength here: every deadline is copied from a file, never invented. See
> Phase 6.

---

## Requirements → coverage

| Rule | roost |
| --- | --- |
| Runs on a Fly.io Sprite | Python HTTP service on the Sprite, deployed via `sprite` CLI |
| Uses ≥1 Sprites connector | **Box + Pinecone**, plus **AgentMail** for the daily email (Phase 6) |
| Built during Hacksgiving week | New repo, clean Nov 23–29 history. All code written this week |
| One entry; submit code + demo + 1–2 sentences, tag @flydotio | See Phase 5 |

---

## How Sprites work (the facts this design rests on; vendor-stated, checked Nov 25 2026)

- **Runtime:** Ubuntu 25.10 Firecracker microVM, 100 GB persistent ext4, arbitrary code. Python/Node/Go
  etc. and coding-agent CLIs preinstalled. Hibernates when idle (scale-to-zero, unbilled);
  **filesystem persists, RAM does not**; warm wake ~100–500 ms, cold 1–2 s.
- **Tested Nov 25 (contradicts the line above for roost):** a running service keeps the Sprite awake,
  so it never scales to zero while `roost` runs. The documented "`--http-port` service auto-starts on
  request" did not happen: after `services stop`, requests returned 502, then timed out, and the
  service stayed `stopped`. `sprite info` showed `cold` while `/proc/uptime` was continuous, so that
  status is not a reliable sign of hibernation.
- **Connectors = keyless creds.** Credential lives in Fly's control plane; the Sprite never holds it.
  Call shape `https://api.sprites.dev/v1/gateway/<provider>/<conn_id>/<path>` with **no** auth header;
  the Sprite is identified by its Fly request signature. Discover ready connections at runtime with
  `curl -s https://api.sprites.dev/v1/gateway/list`. Default-deny; granted in the dashboard by Sprite
  label / name prefix.
- **No native cron found** — wake is by HTTP request. So roost is *triggered* (manual curl for the
  demo; phone shortcut or external cron for "daily" later).
- **Caveat:** egress is permissive — isolation protects *other* Sprites, not the open internet. Nothing
  sensitive goes on the box; connectors hold all secrets.

---

## Phase 0 — $0 accounts & local prep

> Goal: Everything needed exists on a free tier before any code.

- [x] Fly.io account on the **Free plan** (covers hackathon compute; "$1 trial, no card")
- [x] **Box** free personal account with a few real docs to archive
- [x] **Pinecone** free **Starter** tier (serverless index, no card). API key kept in local `.env`
      (gitignored) — local use only, never copied to the Sprite
- [x] `~/Projects/aestart/roost` repo (`git init -b main`), README stub, this plan

## Phase 1 — Sprite up & reachable

> Goal: An empty Sprite running a "hello" HTTP service I can hit from my phone.

- [x] Install CLI: `curl -fsSL https://sprites.dev/install.sh | sh` · `sprite login`
- [x] `sprite create --skip-console --label env=hacksgiving roost` · `sprite use roost`
      → `https://roost-b6xbd.sprites.app`
- [x] Minimal `service.py` (stdlib `http.server`) returning `ok`; run it as a hibernation-surviving
      service: `sprite-env services create roost --cmd python3 --args /home/sprite/roost/service.py
      --dir /home/sprite/roost --http-port 8080` (Sprite user is `sprite`, not root)
- [x] `sprite config update --url-auth public` → confirm the public URL responds
- [x] ~~Prove persistence: write a file, force idle, wake, file still there~~ Not needed (Nov 26):
      couldn't force a real pause (see the Nov 25 test note above), and the decision below keeps the
      service always running, so the Sprite never sleeps during judging. State is on disk regardless
- [x] **Decision (Nov 25):** leave the `roost` service always running, so the Sprite stays awake
      through judging. Check the Fly dashboard usage page to confirm it fits the Free plan.

## Phase 2 — Grant & verify connectors

> Goal: `GET /v1/gateway/list` on the Sprite shows Box and Pinecone ready.

- [x] Dashboard: Org → Connectors → grant **Box** and **Pinecone** to label `env=hacksgiving`
      (Sprite Labels field takes the label exactly as stored: `env=hacksgiving`)
- [x] On the Sprite: `sprite exec --no-stdin -- curl -s https://api.sprites.dev/v1/gateway/list` lists both
      with their `gateway_base_url` + `usage_snippet`
- [x] Smoke-test one call per connector: Box `GET /2.0/folders/0/items` → 200; Pinecone `GET /indexes` → 200
- [x] ~~Create Pinecone index `roost` **in the Pinecone console**~~ — superseded in Phase 3: the console
      makes a document-schema index, which the connector can't search. See Phase 3. (the connector returns 403 "endpoint is
      not supported" for index creation): serverless, aws `us-east-1`, integrated `llama-text-embed-v2`
      (1024, cosine) on field `chunk_text`
- [x] Box download works through the gateway: `GET /2.0/files/<id>/content` → 200 with the bytes, no
      redirect handling needed. Source docs live in Box folder `roost/`
- [x] Decision engine for Phase 4: **rules template** (no Gemini, no model connector)

## Phase 3 — Ingest path (Box → nest)

> Goal: `POST /ingest` loads my Box docs into Pinecone, incrementally.

- [x] List files via the Box connector; fetch text for supported types (`.md`, `.markdown`, `.txt`)
- [x] Embed + upsert into Pinecone (use Pinecone's **hosted embeddings** so no separate embedder — keeps
      it $0 and connector-only), one namespace `me`
- [x] Track a cursor in `nest.json` (persistent fs) so re-ingest only touches new/changed files
- [x] Idempotent: running `/ingest` twice adds nothing the second time

> **Nov 25 result:** first `/ingest` added 8 files / 47 chunks in 34 s; the second run changed nothing
> (1.3 s). The connector forwards `/embed` and the vectors API but **not** the 2026-07 documents API, and
> the console-made `roost` index has a document schema that rejects vector reads. So roost embeds via
> `/embed` and stores plain vectors (chunk text in metadata) in **`roost-nest`**: a plain dense index
> (1024, cosine, aws us-east-1) created from the laptop with the `.env` key. The old `roost` index is
> unused and can be deleted in the console.

## Phase 4 — Ask / triage path (nest → typed decision)

> Goal: `GET /ask?q=...` returns a **structured** answer over retrieved context.

- [x] Query Pinecone for top-k chunks relevant to `q`
- [x] Make the typed decision from `q` + context with a rules template and a fixed output
      schema: `{ answered: bool, source_file: str, category: enum, priority: enum, next_action: enum,
      due: date, action_item: str, confidence, evidence, matches, summary }`
- [x] Return that JSON (+ a one-line template rendered from the typed fields — the engine decides,
      the template phrases)
- [x] Append each answer to `history/` in the nest (`data/history/YYYY-MM-DD.jsonl` on the Sprite)
- [x] Shared secret: `/ingest` and `/ask` require `X-Roost-Token`; the Sprite stores only its SHA-256

> **Nov 25 result:** answered threshold 0.28 (on-topic questions scored 0.36–0.50, off-topic ≤ 0.18).
> Live answers on the sample docs: lease → high / act_now (notice due 2 Dec); car insurance →
> medium / follow_up (call by 10 Dec); trip → high / act_now (buy insurance this week); recipe →
> low / review; "who won the football match" → not answered.

## Phase 5 — Demo, post, submit (before 08:00 WAT Mon Nov 30)

> Goal: A submittable entry with a clean, honest story.

- [x] `README`: what it does, the two connectors, run steps, the "triggered not scheduled" caveat
- [x] Web page at `GET /` (Swiss Data Sheet design via impeccable): token field, sample questions, decision
      sheet, nest list, re-ingest. Token-only access; judges get a token on request. **Superseded Nov 26** by
      the multi-user dark page (Phase 6); the token page and its routes are gone
- [ ] 60–90 s screen demo (Playwright recording with labels), new story: sign in → try samples → Coming up →
      upload a PDF bill → reminder email → ask → delete account (video = "bonus points" per rules)
- [x] `sprite checkpoint create --comment "MVP working"` before recording (checkpoint `v5`, Nov 25)
- [ ] Upload the demo (YouTube unlisted or Loom) for the form's demo link (owner)
- [ ] Post on X / Bluesky / LinkedIn / Reddit with the demo, **tag @flydotio**
- [ ] Submit the form: code link + demo link + 1–2 sentence description
- [ ] Keep Sprite + connectors live through Dec 1 (judging)
- [ ] Check the daily reminder run each morning, Nov 27 – Dec 1 (`gh run list --workflow daily.yml --limit 1`;
      GitHub also emails the owner when a scheduled run fails)

## Phase 6 — "Never miss what's due", multi-user (Nov 25 → Nov 28)

> Goal: anyone can sign in with their email, add their own documents, see everything that is due
> across them, and get a daily reminder email, without being asked. Decided Nov 25 with the owner:
> email sign-in (link + 6-digit code, no passwords), reminders go to the verified sign-in address,
> 10 files / 10 MB per user, 40 users, all user data deleted after judging (Dec 1). The approved dark
> one-column design is the base. This reverses the earlier "no auth UI, no multi-user" non-goal.

### Verified so far (Nov 25)

- AgentMail connector is granted to `env=hacksgiving`. The key is scoped to the inbox
  `roost-nest@agentmail.to`. `GET /v0/auth/me` → 200; `POST /v0/inboxes/roost-nest@agentmail.to/messages/send`
  → 200, and the self-test arrived. Free tier: 100 emails/day **total** (sign-in + reminders), 3,000/month.
- Box connector: list, download, folder create, upload and replace content all work (build step 2).
  Deletion and rename are not forwarded.
- PDF: no extractor on the Sprite, but passwordless `sudo` works, so `poppler-utils` (`pdftotext`)
  can be installed. Optional; decide after the core works.

### How it works

**Sign-in (no passwords).** `POST /api/auth/start {email}` → roost emails a sign-in link and a 6-digit
code from `roost-nest@agentmail.to`. `GET /auth?t=<token>` or `POST /api/auth/verify {email, code}` →
a session cookie. Rules:
- Link token: 32 random bytes; code: 6 digits; both stored only as SHA-256; expire after 15 minutes;
  single use; at most 5 code attempts per request.
- Rate limits: 3 sign-in emails per address per hour, 20 per hour overall; a new account only while
  fewer than 40 users exist (existing users can always sign in).
- Session: random 32-byte id, stored hashed, 30-day expiry. Cookie `roost_session`: `HttpOnly`,
  `Secure`, `SameSite=Lax`, `Path=/`. Every state-changing `/api/*` request must also carry
  `X-Requested-With: roost` (CSRF guard; HTML forms can't set it).
- `POST /api/auth/signout` deletes the session.
- The page says: check your spam folder; the code works even if the link opens in another browser.

**Per-user data, kept apart.** User id = random 12 hex chars.
- Box: `roost/users/<uid>/` (created on first upload).
- Pinecone: index `roost-nest`, namespace `u-<uid>`.
- Sprite: `data/users/<uid>/nest.json` (same shape as today, plus each file's due items);
  `data/accounts.json` (uid, email, created, reminders on/off, last digest date);
  `data/sessions.json`, `data/signin.json` (hashed tokens). All written atomically.
- Limits: 10 files and 10 MB per user, 5 MB per file; types `.md`, `.markdown`, `.txt`, `.docx`
  (`.pdf` if poppler is installed). Enforced on the server, shown on the page.

**Documents.**
- `POST /api/upload` (raw body, `X-Filename` header): check type and limits → Box upload into the
  user's folder → ingest that user's folder → return the updated document list.
- `POST /api/samples`: copy the eight fictional `sample-docs/` into the user's folder (counts toward
  the limit), then ingest. This is the one-click demo for judges.
- `POST /api/documents/<id>/delete`: remove its vectors, drop it from the user's state, and replace
  its Box content with an empty file (the connector won't delete). The owner clears empty files in
  Box later; the cleanup script removes everything after Dec 1.
- `POST /api/sync`: re-ingest the user's folder (picks up edits made directly in Box).

**What's due.**
- At ingest, each file's dated items are extracted and stored in the user's `nest.json`: the to-do
  bullets the rules already find, **plus** any line with a date and a deadline word ("pay by 12 Dec",
  "renews on 15 December", "due", "expires", "deadline", "before"). Each item: file, exact line,
  due date, urgency, next step.
- `GET /api/due?days=N`: the signed-in user's upcoming items, soonest first, grouped on the page as
  overdue / this week / later. No Pinecone calls; it reads the user's state.
- `GET /api/ask?q=`: the existing question flow, scoped to the user's namespace and state.

**Reminders.**
- `POST /internal/digest` (owner token `X-Roost-Token`, as today): for every user with reminders on,
  email the items due in the next 7 days (plus overdue). At most one per user per day; an empty week
  sends nothing. Plain-text + simple HTML, with a link back to roost.
- `POST /internal/sync-all` (owner token): re-ingest every user's folder before the digest.
- Trigger: `.github/workflows/daily.yml`, a scheduled GitHub Actions workflow (free on a public
  repo), calls sync-all then digest each morning (07:00 WAT). Repo secret `ROOST_TOKEN`.
- `POST /api/settings {reminders: bool}` and `POST /api/digest/test` (send me one now; counts toward
  the daily cap).

**Page (dark, one column).**
- Signed out: what roost does in two lines, a three-step explainer, the email sign-in box, then the
  code box. A plain notice: "Demo service. Your files are stored in the roost owner's Box account.
  Don't upload anything sensitive. Everything is deleted after 1 December."
- Signed in, in order: **Coming up** (or an empty state with "Add a document" / "Try it with sample
  documents"), **Your documents** (list, Add, delete, storage used "3 of 10 files · 1.2 of 10 MB"),
  **Reminders** (on/off, which address, "Send me one now"), **Ask a question** (secondary), sign out.
- The old shared access code and `/ask`, `/nest`, `/ingest` owner endpoints are retired; the owner
  token is kept only for `/internal/*`.

**Preview before deploy (decided Nov 25: no second Sprite).** New server code ships additively to the
live `roost` Sprite under new routes (`/api/*`, `/auth`, `/internal/*`) while `/` keeps serving the
current page, so nothing visible changes. The owner checks the new page in the local preview
(`scripts/preview.py`, which serves `web/` locally and forwards API calls to the live Sprite), then the
new page replaces `/`. This is safe because nobody uses the live site before submission. After
submission the live site is frozen until judging ends (a staging Sprite only if changes are needed).

### Build order (cut from the bottom if time runs short)

- [x] 1. Plan updated (this section)
- [x] 2. Probe Box folder create, upload, replace-content and rename through the connector. Nov 25:
      create folder ✓ (409 returns the existing id), upload ✓, same-name upload = new version of the
      same file ✓, replace with empty content ✓ (size 0), **rename ✗ (403 not supported)**. So delete =
      empty the file; ingest already skips empty files. Probe left `roost/users/_probe/probe.txt` (empty)
- [x] 3. `mail.py` (AgentMail send) and `accounts.py` (users, sign-in tokens, sessions, rate limits) + tests
- [x] 4. Per-user ingest: folder and namespace parameters in `ingest.py` / `nest.py`; due-item
      extraction (`due.py`) with the wider date rules + tests
- [x] 5. API routes in `service.py`: auth, me, due, documents, upload, samples, delete, sync, ask,
      settings; CSRF and cookie handling + route tests
      Nov 26: server code deployed additively (`./scripts/deploy.sh api`); live page unchanged. Real
      end-to-end run on the live Sprite, signed in as `roost-nest@agentmail.to` so codes and reminders
      land in a readable inbox: code email ✓, verify ✓, samples (8) ✓, due list ✓, upload + ask ✓,
      test reminder email ✓, delete ✓, sign out ✓. 64 tests pass.
- [x] 6. Page: signed-out and signed-in dashboard on the dark design; check in the local preview
- [x] 6a. Test hygiene (Nov 26). The first live run left its test account behind (1 of 40 slots, 8
      sample files, vectors, a live 30-day session). Fix:
      - `accounts.delete_user` + `userspace.erase`: empty every Box file in the user's folder (the
        connector can't delete or rename), delete-all vectors in `u-<uid>`, remove `data/users/<uid>`,
        drop the account, its sessions and pending sign-ins
      - `POST /api/account/delete` (signed-in user erases themself) and owner-only
        `POST /internal/delete-user {email}` / `{all: true}` (also covers step 12)
      - `scripts/smoke.py` on the Sprite: real sign-in through the roost inbox, samples, due, upload,
        ask, test reminder, then deletes its own account. ~2 emails, 0 slots left behind. Runs once per
        deployed code version (hash of the code on the Sprite) unless `--force`
      - Erase the leftover test account now; remove the stored test session
      - Box folders and emptied file names stay (connector limit); delete `roost/users` in the Box web
        app after Dec 1
      Done Nov 26: leftover test account erased (8 files emptied, vectors cleared, 0 users, 0 sessions);
      `./scripts/smoke.sh` passed 13/13 live and left 0 users, 0 sessions, no `u-*` namespaces; a
      second run on the same code is refused. 67 tests pass.
      Then: tests never use real users' limits. A sign-in request carrying the owner token is a test
      sign-in: it skips the per-email and global hourly limits and the user cap, and doesn't count
      towards them; the account is marked `test` (no daily digest). Email budgets are split: users 90 a
      day, tests 8 (`mail.send(kind=...)`); rebalanced the same day to users 88, tests 10. `smoke.sh` sends the token over stdin, never stored on the
      Sprite. Page got a "Delete my account" section (inline confirm). 72 tests pass.
- [x] 7. Reminders: digest, `/internal/*`, GitHub Actions workflow, "send me one now"
- [x] 8. `.docx` extraction (stdlib `zipfile` + XML)
- [x] 9. Deploy to `roost`, end-to-end test with a real sign-in, checkpoint. Nov 26: full deploy (new page
      live), `smoke.sh` 13/13 with the test path, live state clean (0 users), checkpoint taken
- [x] 10. Docs: README, AGENTS.md, PRODUCT.md, DESIGN.md (dark), plan
- [x] 11. Optional: PDF via `poppler-utils`; forward-a-bill-by-email into the inbox (text only; see F5, F6)
- [ ] 12. After judging (Dec 1): `POST /internal/delete-user {all: true}`, then delete `roost/users` in the
      Box web app

### Finishing batch (Nov 26, agreed with the owner; order chosen so docs are written once)

- [x] F1. Daily schedule: `.github/workflows/daily.yml` (cron 06:00 UTC = 07:00 WAT, plus manual run)
      calls `POST /internal/sync-all` then `POST /internal/digest` with the `ROOST_TOKEN` repo secret
      (owner added it Nov 26). Pushing is needed for it to run
- [x] F2. Retire the single-user owner routes `GET /ask`, `GET /nest`, `POST /ingest`; clear the `me`
      namespace (47 vectors) and its `data/nest.json` + `data/history/` on the Sprite
- [x] F3. Phase 1 "prove persistence" item: mark not needed (service always on) with the reason
- [x] F4. Delete the local `backup/pre-trim` branch
- [x] F5. PDF: install `poppler-utils` on the Sprite (apt), test real PDFs end to end
- [x] F6. Forward a bill: email from your sign-in address to `roost-nest@agentmail.to` becomes a
      document in your space (body as text, plus readable attachments). Read on "Check for changes" and
      in the daily run; only senders that match an account; processed message ids kept on disk; limits
      apply. Page tells users the address
      Done Nov 26: `inbox.py`. The AgentMail connector forwards list/get message but **not** the
      attachment endpoints (403 "endpoint is not supported"), and the Sprite holds no key, so only the
      email's text is read (HTML-only mail is converted); attachments are reported back as "upload
      instead". PDF line-joining fixed for layout text (`due._continues`). Gateway GETs retry on
      502/503/504. Smoke test now forwards a bill too: 15/15 live. 79 tests pass
- [x] F7. Accessibility and quality pass on the page (impeccable audit), fix what it finds. Nov 26:
      axe (WCAG 2.2 AA + best practice) 0 violations signed out and in, desktop and phone, after
      fixes: **phone sign-in inputs collapsed to 23px** (`flex: 1` with a 0 basis in a column row),
      no h1 when signed in, pills 40→44px, switch and logo hit areas, focus lost after inline remove
      confirm, usage bar animated `width` (now `scaleX`). Detector clean after the DESIGN.md rewrite
- [x] F8. Docs: README, AGENTS.md, PRODUCT.md, DESIGN.md + `.impeccable/design.json` for the dark design
- [x] F9. Live run-through on desktop and phone (real browser, test sign-in), then delete the account.
      Nov 26: sign-in by code, samples (10 items), **PDF upload on live** (bill.pdf: 2 dates, the 12 Dec
      payment in Coming up), reminders switch, send me one now, ask, check for changes, phone layout (no
      overflow), remove, delete account; no page errors, no 5xx. Found and fixed: a smoke run's leftover
      forwarded email landed in the next test account (smoke mail now counts only for 30 minutes and has
      a unique name). Live state after: 0 users, 0 sessions, no vectors. Checkpoint taken
- [x] F10. Plan update, commit and push

- [x] F11. Nov 26 fix after an owner test: "What is my Deel contract like?" against an uploaded 40-chunk
      contract PDF was "No answer found" (best score 0.236 < 0.28). Causes: the file name ("deel-…-contract")
      was never embedded, `pdftotext -layout` padded justified text with space runs, and the threshold was
      tuned on short notes. Fix: each chunk is embedded as "Document: <name>\n<chunk>" (stored text
      unchanged; `EMBED_VERSION` 2 re-embeds old files once), and PDF space runs are collapsed. Measured
      on the Sprite: that question 0.224 → 0.374 (answered); sample on-topic questions mostly up (lease
      0.359 → 0.396), off-topic unchanged or down (capital of France 0.179 → 0.084), same file chosen
      for all ten. 82 tests pass

- [x] F12. Rerank first, similarity as fallback (agreed Nov 26). Ask: Pinecone query top 8 (unchanged),
      then `bge-reranker-v2-m3` through the Pinecone connector (`POST /rerank`, keyless; Starter: 500
      requests/month, 60/min) re-scores those 8 (each sent as "Document: <name>" + chunk). The reranked
      best picks the file and its score decides "answered" against a cut-off **calibrated on the Sprite**
      (samples, the Deel contract, tricky and plain off-topic questions). Fallback to today's order and
      0.28 cut-off when the monthly budget is spent (roost counts: users 430, tests 20, in
      `data/rerank_log.json`), or on 429/5xx/timeout. Decisions carry `ranked_by` (rerank | similarity).
      Coming up and reminders don't search, so they never use the allowance. Show before/after scores
      to the owner before deploying
      Built Nov 26 (`rerank.py`, `Nest.rerank`, `ask.py`); not yet deployed. Calibration (16 questions,
      16 of the month's 500): the reranker is sure on specific questions (0.30-0.91), near zero
      off-topic (<= 0.025), but low on broad ones ("what is my lease like" 0.004), so answered =
      rerank >= 0.10, or similarity >= 0.28 and rerank >= 0.002. Same 9/9 on-topic answered; wrong
      answers on off-topic/tricky 2 → 1 (gym membership now rejected). 88 tests pass
      Deployed Nov 26 (server only). Live on the owner's test account: "What is my Deel contract like?"
      answered (rerank 0.06, similarity 0.374), "when can the contract be terminated" answered from the
      termination chunk (rerank 0.509), "when is my gym membership due" rejected (rerank 0.0). Usage
      log: calibration 16, user 3. Smoke test (adds a rerank check) waits for the test email budget to
      reset at 00:00 UTC

**Then Phase 5 continues** with the new story: demo (Playwright with labels), post tagging
@flydotio, form.

---

## Tech stack & cost

| Piece | Choice | Why | Cost |
| --- | --- | --- | --- |
| Host | Fly.io Sprite | Required; persistent + scale-to-zero | $0 (free plan) |
| Service | Python stdlib (`http.server`) | Preinstalled, zero deps, deploys in minutes | $0 |
| Source | **Box** connector | Personal docs, legible demo, judge connector | $0 (free personal) |
| Memory | **Pinecone** connector (+ hosted embeddings) | Vector nest = persistent semantic recall | $0 (Starter) |
| Decision | Rules template | Typed, schema'd triage over context (not prose) | $0 |
| Reminders + sign-in | **AgentMail** connector (`roost-nest@agentmail.to`) + GitHub Actions schedule | Sign-in codes and the daily "due soon" email | $0 (100 emails/day total) |
| Creds | Sprites connector gateway | Sprite never holds a key | $0 |

**Non-goals:** no passwords, no framework, no DB beyond Pinecone and JSON files on the Sprite,
no TypeSafe AI, no Gemini or other model connector. (Multi-user with email sign-in was added in
Phase 6, reversing the original "no auth UI, no multi-user".)

## Risks / honesty

- **$0 hinges on free tiers** — Fly Free, Box personal, Pinecone Starter are confirmed free. The
  decision step is a rules template, so it adds no cost.
- **"Built this week":** clean Nov 23–29 commit history; all code written this week.
- **Scheduled from outside:** Sprites have no native cron, so a GitHub Actions schedule calls the Sprite
  each morning. If that is late or skipped (Actions schedules can be delayed), the page still shows
  "Coming up" on demand.
- **Email budget:** AgentMail free is 100 emails/day across sign-ins and reminders, hence 40 users and
  sign-in rate limits. Sign-in mail from a new `@agentmail.to` address may land in spam.
- **Other people's documents:** uploads land in the owner's Box account. The page says so, and all
  user data is deleted after judging.
- **Rules only see what is written:** documents without dates or to-do lines produce no reminders.
  The page says so instead of guessing.
- **Time budget:** Box+Pinecone MVP is an afternoon and is
  a complete entry on its own.

---

## Sources
- https://fly.io/hacksgiving/ · https://fly.io/sprites/ · https://docs.fly.io/sprites
- https://fly.io/connectors · https://docs.fly.io/sprites/concepts/connectors
- https://docs.fly.io/sprites/cli/commands.md · https://fly.io/sprites/ecosystem/
