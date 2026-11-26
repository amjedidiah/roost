"""Ingest: Box folder -> chunks -> embeddings -> Pinecone, tracked in nest.json.

Re-ingest is incremental: a file is re-embedded only when its Box sha1 or name
changes. Files removed from Box have their chunks deleted from the nest. State
is saved after every file, so a crash mid-run loses at most one file's work.
"""

import datetime as dt
import json
import os
import re
from pathlib import Path

from due import extract_items
from extract import ExtractError, supported_extensions, text_from

BOX_FOLDER = os.environ.get("ROOST_BOX_FOLDER", "roost")
MAX_CHUNK = 1200  # characters; well under the embedding model's token limit
STATE_VERSION = 1


def data_dir():
    return Path(os.environ.get("ROOST_DATA", Path(__file__).resolve().parent / "data"))


# --- state -------------------------------------------------------------------

def load_state(path):
    try:
        state = json.loads(path.read_text())
    except FileNotFoundError:
        state = {}
    state.setdefault("version", STATE_VERSION)
    state.setdefault("box_folder_id", None)
    state.setdefault("files", {})
    return state


def save_state(path, state):
    """Write atomically so a crash never leaves a half-written nest.json."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    os.replace(tmp, path)


# --- chunking ----------------------------------------------------------------

_HEADING = re.compile(r"^#{1,6}\s+(.*)$")


def _split_long(text, limit):
    """Split an over-long paragraph on sentence ends, then hard-wrap if needed."""
    pieces, current = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        while len(sentence) > limit:
            pieces.append(sentence[:limit])
            sentence = sentence[limit:]
        if current and len(current) + 1 + len(sentence) > limit:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def chunk_text(text, max_chars=MAX_CHUNK):
    """Split Markdown or plain text into chunks of at most `max_chars`.

    Paragraphs are packed together up to the limit. Each chunk starts with the
    heading it sits under, so it still makes sense when retrieved on its own.
    """
    blocks, heading = [], ""
    for para in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        para = para.strip()
        if not para:
            continue
        first, _, rest = para.partition("\n")
        match = _HEADING.match(first)
        if match:
            heading = match.group(1).strip()
            para = rest.strip()
            if not para:
                continue
        blocks.append((heading, para))

    chunks, current, current_heading = [], "", None
    for heading, para in blocks:
        prefix = f"{heading}\n" if heading else ""
        room = max_chars - len(prefix)
        for piece in (_split_long(para, room) if len(para) > room else [para]):
            if current and heading == current_heading and len(current) + 2 + len(piece) <= max_chars:
                current += "\n\n" + piece
            else:
                if current:
                    chunks.append(current)
                current, current_heading = prefix + piece, heading
    if current:
        chunks.append(current)
    return chunks


# --- ingest ------------------------------------------------------------------

def chunk_ids(file_id, start, stop):
    return [f"{file_id}#{i}" for i in range(start, stop)]


def ingest(box, nest, state_path=None, folder_id=None, today=None):
    """Sync one Box folder into one Pinecone namespace (the `nest`), tracked in `state_path`.
    With no folder_id, the folder named ROOST_BOX_FOLDER in the Box root is used."""
    state_path = state_path or data_dir() / "nest.json"
    today = today or dt.datetime.now(dt.timezone.utc).date()
    state = load_state(state_path)
    supported = supported_extensions()
    summary = {"added": [], "updated": [], "unchanged": 0, "removed": [], "skipped": [],
               "chunks_upserted": 0, "chunks_deleted": 0}

    folder_id = folder_id or state["box_folder_id"] or box.find_folder(BOX_FOLDER)
    if not folder_id:
        raise LookupError(f"no Box folder named '{BOX_FOLDER}' in the root folder")
    state["box_folder_id"] = folder_id

    seen = set()
    for item in box.folder_items(folder_id):
        if item.get("type") != "file":
            continue
        name = item["name"]
        ext = (item.get("extension") or "").lower()
        if name.startswith("."):
            continue  # .DS_Store and friends
        if ext not in supported:
            summary["skipped"].append({"name": name, "reason": f"unsupported type .{ext or '?'}"})
            continue

        file_id = item["id"]
        seen.add(file_id)
        prev = state["files"].get(file_id)
        if prev and prev["sha1"] == item.get("sha1") and prev["name"] == name and "due" in prev:
            summary["unchanged"] += 1
            continue

        try:
            text = text_from(name, box.download(file_id))
        except ExtractError as e:
            summary["skipped"].append({"name": name, "reason": str(e)})
            seen.discard(file_id)
            continue
        chunks = chunk_text(text)
        if not chunks:
            summary["skipped"].append({"name": name, "reason": "no text"})
            seen.discard(file_id)
            continue

        vectors = nest.embed(chunks, "passage")
        nest.upsert([
            {"id": cid, "values": vec, "metadata": {
                "file_id": file_id, "file_name": name, "chunk_index": i,
                "chunk_text": chunk, "modified_at": item.get("modified_at", ""),
            }}
            for i, (cid, chunk, vec) in enumerate(zip(chunk_ids(file_id, 0, len(chunks)), chunks, vectors))
        ])
        summary["chunks_upserted"] += len(chunks)

        if prev and prev["chunks"] > len(chunks):
            stale = chunk_ids(file_id, len(chunks), prev["chunks"])
            nest.delete(stale)
            summary["chunks_deleted"] += len(stale)

        state["files"][file_id] = {"name": name, "sha1": item.get("sha1"), "chunks": len(chunks),
                                   "modified_at": item.get("modified_at", ""), "size": item.get("size", 0),
                                   "due": extract_items(chunks, today)}
        summary["updated" if prev else "added"].append(name)
        save_state(state_path, state)

    for file_id in [f for f in state["files"] if f not in seen]:
        gone = state["files"].pop(file_id)
        if gone["chunks"]:
            nest.delete(chunk_ids(file_id, 0, gone["chunks"]))
            summary["chunks_deleted"] += gone["chunks"]
        summary["removed"].append(gone["name"])

    save_state(state_path, state)
    summary["files_in_nest"] = len(state["files"])
    return summary
