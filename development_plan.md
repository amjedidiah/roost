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

---

## Requirements → coverage

| Rule | roost |
| --- | --- |
| Runs on a Fly.io Sprite | Python HTTP service on the Sprite, deployed via `sprite` CLI |
| Uses ≥1 Sprites connector | **Box + Pinecone** (both judge/partner connectors) |
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
- [ ] Prove persistence: write a file, force idle, wake, file still there
      (blocked: couldn't force a real pause; see the Nov 25 test note above)
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

- [ ] `README`: what it does, the two connectors, run steps, the "triggered not scheduled" caveat
- [ ] 60–90 s screen demo: `/ingest` my Box docs → `/ask` → show the typed decision → re-ask to show
      the nest remembers (video = "bonus points" per rules)
- [ ] `sprite checkpoint create --comment "MVP working"` before recording
- [ ] Post on X / Bluesky / LinkedIn / Reddit with the demo, **tag @flydotio**
- [ ] Submit the form: code link + demo link + 1–2 sentence description
- [ ] Keep Sprite + connectors live through Dec 1 (judging)

---

## Tech stack & cost

| Piece | Choice | Why | Cost |
| --- | --- | --- | --- |
| Host | Fly.io Sprite | Required; persistent + scale-to-zero | $0 (free plan) |
| Service | Python stdlib (`http.server`) | Preinstalled, zero deps, deploys in minutes | $0 |
| Source | **Box** connector | Personal docs, legible demo, judge connector | $0 (free personal) |
| Memory | **Pinecone** connector (+ hosted embeddings) | Vector nest = persistent semantic recall | $0 (Starter) |
| Decision | Rules template | Typed, schema'd triage over context (not prose) | $0 |
| Creds | Sprites connector gateway | Sprite never holds a key | $0 |

**Non-goals:** no auth UI, no multi-user, no framework, no DB beyond Pinecone,
no TypeSafe AI, no Gemini or other model connector.

## Risks / honesty

- **$0 hinges on free tiers** — Fly Free, Box personal, Pinecone Starter are confirmed free. The
  decision step is a rules template, so it adds no cost.
- **"Built this week":** clean Nov 23–29 commit history; all code written this week.
- **Triggered, not scheduled:** MVP runs on demand (no native Sprite cron); README says so and points at
  the webhook/phone-cron path as the productionization step.
- **Time budget:** Box+Pinecone MVP is an afternoon and is
  a complete entry on its own.

---

## Sources
- https://fly.io/hacksgiving/ · https://fly.io/sprites/ · https://docs.fly.io/sprites
- https://fly.io/connectors · https://docs.fly.io/sprites/concepts/connectors
- https://docs.fly.io/sprites/cli/commands.md · https://fly.io/sprites/ecosystem/
