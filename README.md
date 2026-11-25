# roost

A personal archivist agent that lives on a [Fly.io Sprite](https://fly.io/sprites/). It pulls your own documents from **Box**, keeps them as vector memory in **Pinecone** (the "nest"), and answers questions with a typed, structured decision: which file answers you, how to categorise it, and what to do next.

The Sprite holds no credentials. Every partner call goes through the Sprites connector gateway.

Built for Hacksgiving 2026.

> **Status:** work in progress. Run steps, endpoints and a demo are coming. See [`development_plan.md`](development_plan.md).

## Endpoints

Both require an `X-Roost-Token` header.

- `POST /ingest` loads `.md` and `.txt` files from the Box `roost/` folder into the nest. It is incremental: a second run with no changes in Box does nothing.
- `GET /ask?q=...` finds the best-matching document and returns a typed JSON decision: which file, category, priority, next action, due date and the to-do item it came from.

```json
{
  "answered": true,
  "source_file": "car-insurance-renewal.md",
  "category": "finance",
  "priority": "medium",
  "next_action": "follow_up",
  "due": "2026-12-10",
  "action_item": "Call Harbourline before 10 December to negotiate; otherwise switch to Bramble.",
  "summary": "car-insurance-renewal.md answers this. Finance, medium priority: Call Harbourline before 10 December to negotiate; otherwise switch to Bramble. (due 10 Dec 2026)"
}
```

The decision is made by fixed rules over your own documents, not by a language model.

## Note

roost is triggered, not scheduled. Sprites wake on HTTP requests and have no native cron, so ingest and ask run on demand.
