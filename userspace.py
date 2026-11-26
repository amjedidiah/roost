"""One user's space: their Box folder, Pinecone namespace and state on disk.

Box:      roost/users/<uid>/           (created on first upload)
Pinecone: index roost-nest, namespace u-<uid>
Sprite:   data/users/<uid>/nest.json   (ingest state, with each file's due items)
          data/users/<uid>/history/    (answers to questions)

Limits are enforced here, before anything is sent to Box.
"""

import datetime as dt
import os
import re
import shutil
import threading
from collections import defaultdict
from pathlib import Path

import accounts
from ask import ask as ask_question
from due import upcoming
from extract import supported_extensions
from ingest import BOX_FOLDER, chunk_ids, data_dir, ingest, load_state, save_state

MAX_FILES = int(os.environ.get("ROOST_MAX_FILES", "10"))
MAX_BYTES = int(os.environ.get("ROOST_MAX_BYTES", str(10 * 1024 * 1024)))
MAX_FILE_BYTES = int(os.environ.get("ROOST_MAX_FILE_BYTES", str(5 * 1024 * 1024)))
SAMPLES = Path(__file__).resolve().parent / "sample-docs"

_locks = defaultdict(threading.Lock)
_users_folder = {}  # RAM cache: id of roost/users in Box


class LimitError(Exception):
    """A request breaks a limit or a rule; the message is safe to show."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def user_dir(uid):
    return data_dir() / "users" / uid


def state_path(uid):
    return user_dir(uid) / "nest.json"


def namespace(uid):
    return f"u-{uid}"


def _folder(uid, box, create):
    """The user's Box folder id, creating roost/users/<uid> when `create`."""
    known = (accounts.get_user(uid) or {}).get("box_folder")
    if known:
        return known
    if not create:
        return None
    if "id" not in _users_folder:
        root = box.find_folder(BOX_FOLDER)
        if not root:
            raise LookupError(f"no Box folder named '{BOX_FOLDER}' in the root folder")
        _users_folder["id"] = box.ensure_folder("users", root)
    folder = box.ensure_folder(uid, _users_folder["id"])
    accounts.update_user(uid, box_folder=folder)
    return folder


def documents(uid):
    files = load_state(state_path(uid))["files"]
    docs = [{"id": fid, "name": f["name"], "size": f.get("size", 0), "sections": f["chunks"],
             "dates": len(f.get("due", [])), "modified_at": f.get("modified_at", "")}
            for fid, f in files.items()]
    return sorted(docs, key=lambda d: d["name"].lower())


def usage(uid):
    docs = documents(uid)
    return {"files": len(docs), "bytes": sum(d["size"] for d in docs),
            "max_files": MAX_FILES, "max_bytes": MAX_BYTES, "max_file_bytes": MAX_FILE_BYTES,
            "types": sorted(supported_extensions())}


def sync(uid, box, make_nest):
    folder = _folder(uid, box, create=False)
    if not folder:
        return {"added": [], "updated": [], "unchanged": 0, "removed": [], "skipped": [],
                "chunks_upserted": 0, "chunks_deleted": 0, "files_in_nest": 0}
    with _locks[uid]:
        return ingest(box, make_nest(namespace(uid)), state_path(uid), folder_id=folder)


SAFE_NAME = re.compile(r"[^\w .,()&'+-]")


def clean_name(name):
    name = Path((name or "").replace("\\", "/")).name.strip()
    name = SAFE_NAME.sub("_", name)[:120].strip()
    if not name or name.startswith("."):
        raise LimitError("That file needs a name.")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in supported_extensions():
        kinds = ", ".join("." + e for e in sorted(supported_extensions()))
        raise LimitError(f"roost can read {kinds} files. This one is .{ext or '?'}.", 415)
    return name


def _check_room(uid, name, size):
    if size == 0:
        raise LimitError("That file is empty.")
    if size > MAX_FILE_BYTES:
        raise LimitError(f"That file is too big. The limit is {MAX_FILE_BYTES // (1024 * 1024)} MB per file.", 413)
    docs = documents(uid)
    existing = next((d for d in docs if d["name"] == name), None)
    files = len(docs) + (0 if existing else 1)
    total = sum(d["size"] for d in docs) - (existing["size"] if existing else 0) + size
    if files > MAX_FILES:
        raise LimitError(f"You can keep up to {MAX_FILES} documents. Delete one to add another.", 413)
    if total > MAX_BYTES:
        raise LimitError(f"You can keep up to {MAX_BYTES // (1024 * 1024)} MB of documents. Delete one to make room.", 413)


def upload(uid, name, data, box, make_nest):
    """Store one file in the user's Box folder and read it into their nest."""
    name = clean_name(name)
    _check_room(uid, name, len(data))
    folder = _folder(uid, box, create=True)
    with _locks[uid]:
        box.upload(folder, name, data)
        return ingest(box, make_nest(namespace(uid)), state_path(uid), folder_id=folder)


def add_samples(uid, box, make_nest):
    """Copy the fictional sample documents into the user's space (skipping ones already there)."""
    have = {d["name"] for d in documents(uid)}
    samples = [p for p in sorted(SAMPLES.glob("*.md")) if p.name not in have]
    if not samples:
        raise LimitError("The sample documents are already in your list.")
    if len(have) + len(samples) > MAX_FILES:
        raise LimitError(f"The samples are {len(samples)} documents and you have room for "
                         f"{MAX_FILES - len(have)}. Delete some to add them.", 413)
    folder = _folder(uid, box, create=True)
    with _locks[uid]:
        for p in samples:
            box.upload(folder, p.name, p.read_bytes())
        return ingest(box, make_nest(namespace(uid)), state_path(uid), folder_id=folder)


def delete(uid, file_id, box, make_nest):
    """Remove a document: its vectors, its state, and its content in Box.

    The Box connector forwards neither delete nor rename, so the file in Box is
    replaced with an empty version; ingest skips empty files from then on.
    """
    with _locks[uid]:
        path = state_path(uid)
        state = load_state(path)
        doc = state["files"].get(file_id)
        if not doc:
            raise LimitError("That document isn't in your list.", 404)
        box.replace(file_id, doc["name"], b"")
        if doc["chunks"]:
            make_nest(namespace(uid)).delete(chunk_ids(file_id, 0, doc["chunks"]))
        state["files"].pop(file_id)
        save_state(path, state)
    return documents(uid)


def erase(uid, box, make_nest):
    """Delete a user and everything they added: Box content, vectors, state, the account.

    The connector can't delete or rename in Box, so each file in the user's folder is
    emptied; the folder and the file names stay until the owner removes roost/users in Box.
    """
    user = accounts.get_user(uid)
    if not user:
        raise LimitError("There is no such account.", 404)
    with _locks[uid]:
        emptied = 0
        folder = user.get("box_folder")
        if folder:
            for item in box.folder_items(folder):
                if item.get("type") == "file" and item.get("size", 1):
                    box.replace(item["id"], item["name"], b"")
                    emptied += 1
        make_nest(namespace(uid)).clear()
        shutil.rmtree(user_dir(uid), ignore_errors=True)
        accounts.delete_user(uid)
    _locks.pop(uid, None)
    return {"email": user["email"], "files_emptied": emptied}


def due(uid, today=None, within_days=60):
    today = today or dt.datetime.now(dt.timezone.utc).date()
    return upcoming(load_state(state_path(uid))["files"], today, within_days)


def ask(uid, question, make_nest):
    return ask_question(question, make_nest(namespace(uid)), state_path(uid), user_dir(uid) / "history")
