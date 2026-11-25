"""The nest: Pinecone through the Sprites connector gateway.

The connector forwards inference (/embed) and the vectors API, but not index
creation or the 2026-07 documents API. So roost embeds text with Pinecone's
hosted model and stores plain vectors with the chunk text in metadata. The
index must be a plain dense index (1024 dims, cosine) without a document schema.
"""

import os

import gateway

API_VERSION = "2025-04"
MODEL = "llama-text-embed-v2"
INDEX = os.environ.get("ROOST_INDEX", "roost-nest")
NAMESPACE = os.environ.get("ROOST_NAMESPACE", "me")
EMBED_BATCH = 96  # max inputs per /embed request for this model
UPSERT_BATCH = 100
DELETE_BATCH = 1000


class Nest:
    def _post(self, path, body):
        return gateway.request(
            "POST",
            gateway.base_url("pinecone") + path,
            body,
            {"X-Pinecone-API-Version": API_VERSION},
        )

    def embed(self, texts, input_type):
        """Embed texts; input_type is 'passage' for documents, 'query' for questions."""
        vectors = []
        for i in range(0, len(texts), EMBED_BATCH):
            resp = self._post("/embed", {
                "model": MODEL,
                "parameters": {"input_type": input_type, "truncate": "END"},
                "inputs": [{"text": t} for t in texts[i:i + EMBED_BATCH]],
            })
            vectors.extend(d["values"] for d in resp["data"])
        return vectors

    def upsert(self, records):
        """records: [{"id", "values", "metadata"}]."""
        for i in range(0, len(records), UPSERT_BATCH):
            self._post(f"/indexes/{INDEX}/vectors/upsert",
                       {"vectors": records[i:i + UPSERT_BATCH], "namespace": NAMESPACE})

    def delete(self, ids):
        for i in range(0, len(ids), DELETE_BATCH):
            self._post(f"/indexes/{INDEX}/vectors/delete",
                       {"ids": ids[i:i + DELETE_BATCH], "namespace": NAMESPACE})

    def query(self, vector, top_k=5):
        resp = self._post(f"/indexes/{INDEX}/query", {
            "namespace": NAMESPACE, "vector": vector, "topK": top_k, "includeMetadata": True,
        })
        return resp.get("matches", [])
