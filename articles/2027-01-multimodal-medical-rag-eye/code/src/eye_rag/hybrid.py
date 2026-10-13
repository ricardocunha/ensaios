"""Hybrid retrieval in Qdrant: dense image vectors + sparse text over per-image reports.

RFMiD has **no free-text reports**: each training image gets a "report" built from its
labels (`vlm.case_report`), and the two result lists are fused with RRF. The query text
must come from labels available at test time (kNN pre-labels or VLM predictions); the
query's true labels are an **oracle**, reported only as an upper bound
(docs/RESULTS.md, 2.2).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

import numpy as np
from qdrant_client import QdrantClient, models

from eye_rag.vlm import case_report

HYBRID = "rfmid_hybrid"
_WORD = re.compile(r"[a-z0-9]+")
STOP = frozenset("a an and the of or with in at by to from for on one all its it is as than into through".split())


def tokenize(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in STOP]


class Vocabulary:
    """Word -> index for sparse vectors. Unknown query words are dropped."""

    def __init__(self, texts: Sequence[str]):
        words = sorted({w for t in texts for w in tokenize(t)})
        self.index = {w: i for i, w in enumerate(words)}

    def sparse(self, text: str) -> models.SparseVector:
        tf = Counter(self.index[w] for w in tokenize(text) if w in self.index)
        idx = sorted(tf)
        return models.SparseVector(indices=idx, values=[float(tf[i]) for i in idx])


def build_hybrid_index(client: QdrantClient, records: Sequence, vectors: np.ndarray, name: str = HYBRID) -> Vocabulary:
    """One point per training image: dense 'image' vector + sparse 'report' vector."""
    reports = [case_report(sorted(r.label_set)) for r in records]
    vocab = Vocabulary(reports)
    if client.collection_exists(name):
        client.delete_collection(name)
    client.create_collection(
        name,
        vectors_config={"image": models.VectorParams(size=vectors.shape[1], distance=models.Distance.COSINE)},
        sparse_vectors_config={"report": models.SparseVectorParams(modifier=models.Modifier.IDF)},
    )
    client.upload_points(
        name,
        [
            models.PointStruct(
                id=i,
                vector={"image": v.tolist(), "report": vocab.sparse(rep)},
                payload={"id": r.id, "labels": sorted(r.label_set), "report": rep},
            )
            for i, (r, v, rep) in enumerate(zip(records, vectors, reports, strict=True))
        ],
    )
    return vocab


def query_text_from_labels(labels: Sequence[str]) -> str:
    """The query-side report: same template as the index side."""
    return case_report(sorted(labels)) if labels else ""


def search(
    client: QdrantClient,
    vocab: Vocabulary,
    queries: np.ndarray,
    texts: Sequence[str] | None,
    k: int,
    prefetch: int = 50,
    name: str = HYBRID,
) -> np.ndarray:
    """Top-k point ids per query. `texts=None` -> dense only; otherwise RRF of dense and
    sparse (a query with empty text falls back to dense only)."""
    out = np.zeros((len(queries), k), dtype=np.int64)
    reqs = []
    for i, q in enumerate(queries):
        sv = vocab.sparse(texts[i]) if texts is not None else None
        if sv is None or not sv.indices:
            reqs.append(models.QueryRequest(query=q.tolist(), using="image", limit=k))
        else:
            reqs.append(
                models.QueryRequest(
                    prefetch=[
                        models.Prefetch(query=q.tolist(), using="image", limit=prefetch),
                        models.Prefetch(query=sv, using="report", limit=prefetch),
                    ],
                    query=models.FusionQuery(fusion=models.Fusion.RRF),
                    limit=k,
                )
            )
    for start in range(0, len(reqs), 128):
        for i, res in enumerate(client.query_batch_points(name, reqs[start : start + 128]), start):
            ids = [p.id for p in res.points]
            if len(ids) < k:  # pad (never happens with >= k indexed points)
                ids += [ids[-1]] * (k - len(ids))
            out[i] = ids[:k]
    return out
