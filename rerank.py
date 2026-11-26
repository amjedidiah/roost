"""Rerank: Pinecone's bge-reranker-v2-m3 re-scores the closest passages, with a budget.

Ask searches by similarity first (the 8 closest chunks), then asks the reranker
how well each one answers the question. The reranker runs through the Pinecone
connector, keyless, on the Starter plan's 500 requests a month (60 a minute).
roost counts its own use in data/rerank_log.json, per month and per kind
("user" and "test", so tests never use what real users need), and stops before
the allowance runs out. Any refusal raises Unavailable, and ask falls back to
similarity alone, which is how roost answered before.

Calibrated Nov 26 on the samples plus a 36-chunk contract PDF (16 questions):
the reranker is sure about passages that answer a specific question (0.30-0.91)
and near zero for off-topic ones (<= 0.025), but it scores broad questions like
"what is my lease like" low too (0.004-0.06), because no one passage answers
them. So "answered" uses both signals: the reranker is sure (>= STRONG), or the
similarity passes the old cut-off and the reranker doesn't reject it (>= FLOOR).
"""

import datetime as dt
import os
import threading

import gateway
from ingest import data_dir
from store import read_json, write_json

MODEL = "bge-reranker-v2-m3"
BUDGETS = {"user": int(os.environ.get("ROOST_RERANK_BUDGET", "430")),
           "test": int(os.environ.get("ROOST_TEST_RERANK_BUDGET", "20"))}
STRONG = float(os.environ.get("ROOST_RERANK_STRONG", "0.10"))
FLOOR = float(os.environ.get("ROOST_RERANK_FLOOR", "0.002"))
_lock = threading.Lock()


class Unavailable(Exception):
    """The reranker can't be used for this question; fall back to similarity."""


def _log_path():
    return data_dir() / "rerank_log.json"


def used(month, kind="user"):
    return read_json(_log_path(), {}).get(month, {}).get(kind, 0)


def _take(month, kind):
    with _lock:
        log = read_json(_log_path(), {})
        counts = log.setdefault(month, {})
        if counts.get(kind, 0) >= BUDGETS[kind]:
            raise Unavailable(f"monthly {kind} rerank budget of {BUDGETS[kind]} spent")
        counts[kind] = counts.get(kind, 0) + 1
        log = {m: c for m, c in log.items() if m >= month[:4]}  # keep this year's months
        write_json(_log_path(), log)


def scores(nest, question, texts, kind="user", today=None):
    """Relevance of each text to the question, in the order given. Raises Unavailable."""
    if kind not in BUDGETS:
        raise ValueError(f"unknown rerank kind {kind!r}")
    if not hasattr(nest, "rerank"):
        raise Unavailable("this nest can't rerank")
    month = (today or dt.datetime.now(dt.timezone.utc).date()).strftime("%Y-%m")
    _take(month, kind)  # Pinecone counts every request, so count before sending
    try:
        return nest.rerank(question, texts, MODEL)
    except gateway.GatewayError as e:
        raise Unavailable(f"rerank failed: {e.status or e}") from None


def answered(best_rerank, best_similarity, similarity_cutoff):
    return best_rerank >= STRONG or (best_similarity >= similarity_cutoff and best_rerank >= FLOOR)
