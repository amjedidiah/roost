"""In-memory stand-ins for Box, Pinecone and email, shared by the multi-user tests."""

import hashlib
import itertools


class FakeBox:
    """Folders and files in memory, with the Box behaviour roost relies on."""

    def __init__(self):
        self._ids = itertools.count(1000)
        self.folders = {"0": {"name": "", "parent": None}}
        self.files = {}  # id -> {name, parent, data}
        self.roost = self.ensure_folder("roost", "0")

    def _id(self):
        return str(next(self._ids))

    def find_folder(self, name, parent_id="0"):
        return next((fid for fid, f in self.folders.items() if f["name"] == name and f["parent"] == parent_id), None)

    def ensure_folder(self, name, parent_id):
        found = self.find_folder(name, parent_id)
        if found:
            return found
        fid = self._id()
        self.folders[fid] = {"name": name, "parent": parent_id}
        return fid

    def folder_items(self, folder_id):
        items = [{"type": "folder", "id": fid, "name": f["name"]}
                 for fid, f in self.folders.items() if f["parent"] == folder_id]
        for fid, f in self.files.items():
            if f["parent"] == folder_id:
                ext = f["name"].rsplit(".", 1)[-1] if "." in f["name"] else ""
                items.append({"type": "file", "id": fid, "name": f["name"], "extension": ext,
                              "size": len(f["data"]), "sha1": hashlib.sha1(f["data"]).hexdigest(),
                              "modified_at": "t"})
        return items

    def download(self, file_id):
        return self.files[file_id]["data"]

    def upload(self, folder_id, name, data):
        existing = next((fid for fid, f in self.files.items() if f["parent"] == folder_id and f["name"] == name), None)
        if existing:
            return self.replace(existing, name, data)
        fid = self._id()
        self.files[fid] = {"name": name, "parent": folder_id, "data": data}
        return {"id": fid, "name": name, "size": len(data)}

    def replace(self, file_id, name, data):
        self.files[file_id]["data"] = data
        return {"id": file_id, "name": self.files[file_id]["name"], "size": len(data)}


class FakeNest:
    """One shared vector store, partitioned by namespace like Pinecone."""

    store = {}

    def __init__(self, namespace=None):
        self.namespace = namespace or "me"
        self.vectors = FakeNest.store.setdefault(self.namespace, {})

    def embed(self, texts, input_type):
        return [[float(len(t))] for t in texts]

    def upsert(self, records):
        for r in records:
            self.vectors[r["id"]] = r

    def delete(self, ids):
        for i in ids:
            self.vectors.pop(i, None)

    def clear(self):
        self.vectors.clear()

    def query(self, vector, top_k=5):
        return []

    def fetch(self, ids):
        return {i: self.vectors[i] for i in ids if i in self.vectors}


class FakeMail:
    def __init__(self):
        self.sent = []

    def __call__(self, to, subject, text, html=None, kind="user"):
        self.sent.append({"to": to, "subject": subject, "text": text, "html": html, "kind": kind})
