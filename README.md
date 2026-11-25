# roost

A personal archivist agent that lives on a [Fly.io Sprite](https://fly.io/sprites/). It pulls your own documents from **Box**, keeps them as vector memory in **Pinecone** (the "nest"), and answers questions with a typed, structured decision: which file answers you, how to categorise it, and what to do next.

The Sprite holds no credentials. Every partner call goes through the Sprites connector gateway.

Built for Hacksgiving 2026.

> **Status:** work in progress. Run steps, endpoints and a demo are coming. See [`development_plan.md`](development_plan.md).

## Endpoints (planned)

- `POST /ingest` loads Box docs into the nest. It is incremental and idempotent.
- `GET /ask?q=...` retrieves relevant context and returns a typed JSON decision.

## Note

roost is triggered, not scheduled. Sprites wake on HTTP requests and have no native cron, so ingest and ask run on demand.
