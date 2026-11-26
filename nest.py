"""The nest: Pinecone through the Sprites connector gateway.

The connector forwards inference (/embed) and the vectors API, but not index
creation or the 2026-07 documents API. So roost embeds text with Pinecone's
hosted model and stores plain vectors with the chunk text in metadata. The
index must be a plain dense index (1024 dims, cosine) without a document schema.
"""

import os
import urllib.parse

import gateway

API_VERSION = "2025-04"
MODEL = "llama-text-embed-v2"
INDEX = os.environ.get("ROOST_INDEX", "roost-nest")
NAMESPACE = os.environ.get("ROOST_NAMESPACE", "me")
EMBED_BATCH = 96  # max inputs per /embed request for this model
UPSERT_BATCH = 100
DELETE_BATCH = 1000
FETCH_BATCH = 100
RERANK_TIMEOUT = 10  # seconds; slower than this and ask falls back to similarity


class Nest:
    def __init__(self, namespace=None):
        self.namespace = namespace or NAMESPACE

    def _post(self, path, body, timeout=gateway.TIMEOUT):
        return gateway.request(
            "POST",
            gateway.base_url("pinecone") + path,
            body,
            {"X-Pinecone-API-Version": API_VERSION},
            timeout=timeout,
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

    def rerank(self, query, texts, model):
        """Relevance score (0-1) of each text to the query, in the order given."""
        resp = self._post("/rerank", {
            "model": model, "query": query, "top_n": len(texts), "return_documents": False,
            "parameters": {"truncate": "END"}, "documents": [{"text": t} for t in texts],
        }, timeout=RERANK_TIMEOUT)
        out = [0.0] * len(texts)
        for row in resp["data"]:
            out[row["index"]] = row["score"]
        return out

    def upsert(self, records):
        """records: [{"id", "values", "metadata"}]."""
        for i in range(0, len(records), UPSERT_BATCH):
            self._post(f"/indexes/{INDEX}/vectors/upsert",
                       {"vectors": records[i:i + UPSERT_BATCH], "namespace": self.namespace})

    def delete(self, ids):
        for i in range(0, len(ids), DELETE_BATCH):
            self._post(f"/indexes/{INDEX}/vectors/delete",
                       {"ids": ids[i:i + DELETE_BATCH], "namespace": self.namespace})

    def clear(self):
        """Delete every vector in this namespace. A namespace that was never written is fine."""
        try:
            self._post(f"/indexes/{INDEX}/vectors/delete", {"deleteAll": True, "namespace": self.namespace})
        except gateway.GatewayError as e:
            if e.status != 404:
                raise

    def fetch(self, ids):
        """Fetch vectors by id. Returns {id: {"id", "values", "metadata"}}; missing ids are absent."""
        found = {}
        for i in range(0, len(ids), FETCH_BATCH):
            params = urllib.parse.urlencode({"ids": ids[i:i + FETCH_BATCH], "namespace": self.namespace}, doseq=True)
            resp = gateway.request(
                "GET",
                f"{gateway.base_url('pinecone')}/indexes/{INDEX}/vectors/fetch?{params}",
                headers={"X-Pinecone-API-Version": API_VERSION},
            )
            found.update(resp.get("vectors", {}))
        return found

    def query(self, vector, top_k=5):
        resp = self._post(f"/indexes/{INDEX}/query", {
            "namespace": self.namespace, "vector": vector, "topK": top_k, "includeMetadata": True,
        })
        return resp.get("matches", [])
