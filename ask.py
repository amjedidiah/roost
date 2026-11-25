"""Ask: question -> nest search -> typed decision, logged to data/history/."""

import datetime as dt
import json

from decide import ANSWER_THRESHOLD, decide
from ingest import chunk_ids, data_dir, load_state

TOP_K = 8


def ask(question, nest, state_path=None, history_dir=None, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    state_path = state_path or data_dir() / "nest.json"
    history_dir = history_dir or data_dir() / "history"

    matches = nest.query(nest.embed([question], "query")[0], top_k=TOP_K)

    # Read the whole best-matching file, so dates and to-dos outside the matched
    # chunks still count. Chunk count comes from the ingest state.
    doc_chunks = []
    if matches and matches[0]["score"] >= ANSWER_THRESHOLD:
        file_id = matches[0]["metadata"].get("file_id")
        count = load_state(state_path)["files"].get(file_id, {}).get("chunks", 0)
        if count:
            ids = chunk_ids(file_id, 0, count)
            fetched = nest.fetch(ids)
            doc_chunks = [fetched[i]["metadata"]["chunk_text"] for i in ids if i in fetched]

    decision = decide(question, matches, doc_chunks, now.date())

    history_dir.mkdir(parents=True, exist_ok=True)
    with (history_dir / f"{now.date().isoformat()}.jsonl").open("a") as f:
        f.write(json.dumps({"at": now.isoformat(timespec="seconds"), **decision}) + "\n")
    return decision
