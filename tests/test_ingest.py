import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from ingest import MAX_CHUNK, chunk_text, ingest


class FakeBox:
    def __init__(self):
        self.files = {}  # id -> (name, text)
        self.downloads = 0

    def put(self, file_id, name, text):
        self.files[file_id] = (name, text)

    def find_folder(self, name, parent_id="0"):
        return "F1" if name == "roost" else None

    def folder_items(self, folder_id):
        items = [{"type": "folder", "id": "sub", "name": "nested"}]
        for fid, (name, text) in self.files.items():
            ext = name.rsplit(".", 1)[-1] if "." in name else ""
            items.append({"type": "file", "id": fid, "name": name, "extension": ext,
                          "sha1": hashlib.sha1(text.encode()).hexdigest(), "modified_at": "t"})
        return items

    def download(self, file_id):
        self.downloads += 1
        return self.files[file_id][1].encode()


class FakeNest:
    def __init__(self):
        self.vectors = {}
        self.embedded = 0

    def embed(self, texts, input_type):
        assert input_type == "passage"
        self.embedded += len(texts)
        return [[float(len(t))] for t in texts]

    def upsert(self, records):
        for r in records:
            self.vectors[r["id"]] = r

    def delete(self, ids):
        for i in ids:
            self.vectors.pop(i, None)


def doc(paragraphs, size=300):
    return "\n\n".join(f"## Section {i}\n" + ("word " * (size // 5)) for i in range(paragraphs))


class IngestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "nest.json"
        self.box, self.nest = FakeBox(), FakeNest()

    def tearDown(self):
        self.tmp.cleanup()

    def run_ingest(self):
        return ingest(self.box, self.nest, self.state)

    def test_first_run_adds_files_and_skips_unsupported(self):
        self.box.put("1", "lease.md", doc(3))
        self.box.put("2", "notes.txt", "hello")
        self.box.put("3", "photo.png", "binary")
        self.box.put("4", ".DS_Store", "junk")
        s = self.run_ingest()
        self.assertEqual(sorted(s["added"]), ["lease.md", "notes.txt"])
        self.assertEqual(s["skipped"], [{"name": "photo.png", "reason": "unsupported type .png"}])
        self.assertEqual(s["files_in_nest"], 2)
        self.assertEqual(len(self.nest.vectors), s["chunks_upserted"])
        meta = self.nest.vectors["2#0"]["metadata"]
        self.assertEqual((meta["file_name"], meta["chunk_text"]), ("notes.txt", "hello"))

    def test_second_run_is_a_no_op(self):
        self.box.put("1", "lease.md", doc(3))
        self.run_ingest()
        downloads, embedded = self.box.downloads, self.nest.embedded
        s = self.run_ingest()
        self.assertEqual((s["added"], s["updated"], s["removed"]), ([], [], []))
        self.assertEqual(s["unchanged"], 1)
        self.assertEqual(s["chunks_upserted"], 0)
        self.assertEqual((self.box.downloads, self.nest.embedded), (downloads, embedded))

    def test_changed_file_is_reembedded_and_stale_chunks_deleted(self):
        self.box.put("1", "lease.md", doc(12))
        first = self.run_ingest()["chunks_upserted"]
        self.box.put("1", "lease.md", "short now")
        s = self.run_ingest()
        self.assertEqual(s["updated"], ["lease.md"])
        self.assertEqual(s["chunks_deleted"], first - 1)
        self.assertEqual(list(self.nest.vectors), ["1#0"])

    def test_rename_updates_metadata(self):
        self.box.put("1", "a.md", "same text")
        self.run_ingest()
        self.box.put("1", "b.md", "same text")
        s = self.run_ingest()
        self.assertEqual(s["updated"], ["b.md"])
        self.assertEqual(self.nest.vectors["1#0"]["metadata"]["file_name"], "b.md")

    def test_removed_file_chunks_are_deleted(self):
        self.box.put("1", "lease.md", doc(3))
        self.box.put("2", "notes.txt", "hello")
        self.run_ingest()
        del self.box.files["1"]
        s = self.run_ingest()
        self.assertEqual(s["removed"], ["lease.md"])
        self.assertTrue(all(k.startswith("2#") for k in self.nest.vectors))
        self.assertNotIn("1", json.loads(self.state.read_text())["files"])

    def test_empty_file_is_skipped_and_old_chunks_removed(self):
        self.box.put("1", "x.md", "text")
        self.run_ingest()
        self.box.put("1", "x.md", "   \n\n  ")
        s = self.run_ingest()
        self.assertIn({"name": "x.md", "reason": "no text"}, s["skipped"])
        self.assertEqual(s["removed"], ["x.md"])
        self.assertEqual(self.nest.vectors, {})

    def test_missing_folder_raises(self):
        self.box.find_folder = lambda name, parent_id="0": None
        with self.assertRaises(LookupError):
            self.run_ingest()


class ChunkTest(unittest.TestCase):
    def test_chunks_respect_limit_and_keep_heading(self):
        text = "# Title\n\nintro\n\n## Costs\n\n" + ("A sentence about money. " * 200)
        chunks = chunk_text(text)
        self.assertTrue(all(len(c) <= MAX_CHUNK for c in chunks))
        self.assertTrue(all(c.startswith("Costs\n") for c in chunks[1:]))
        self.assertEqual(chunks[0], "Title\nintro")

    def test_short_paragraphs_under_one_heading_are_packed(self):
        chunks = chunk_text("## H\n\none\n\ntwo\n\nthree")
        self.assertEqual(chunks, ["H\none\n\ntwo\n\nthree"])

    def test_unbroken_text_is_hard_wrapped(self):
        chunks = chunk_text("x" * 3000)
        self.assertTrue(all(len(c) <= MAX_CHUNK for c in chunks))
        self.assertEqual("".join(chunks), "x" * 3000)

    def test_blank_text_has_no_chunks(self):
        self.assertEqual(chunk_text(" \n\n \n"), [])


if __name__ == "__main__":
    unittest.main()
