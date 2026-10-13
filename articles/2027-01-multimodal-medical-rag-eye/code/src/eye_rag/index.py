"""A local Qdrant index (embedded mode: a folder on disk, no server).

Two collections: `rfmid_images` (one point per image; payload labels are the condition
codes, or ["NORMAL"]) and `rfmid_labels` (one text-embedded point per condition, not
used by the baselines).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np
from qdrant_client import QdrantClient, models

from eye_rag.labels import CONDITIONS, NORMAL, NORMAL_DESCRIPTION

QDRANT_PATH = Path("data/qdrant")
IMAGES = "rfmid_images"
LABELS = "rfmid_labels"


def open_client(path: Path | str = QDRANT_PATH) -> QdrantClient:
    """`":memory:"` gives a throwaway in-memory index (used by the tests)."""
    if str(path) == ":memory:":
        return QdrantClient(location=":memory:")
    Path(path).mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=str(path))


def _recreate(client: QdrantClient, name: str, vector_name: str, dim: int) -> None:
    if client.collection_exists(name):
        client.delete_collection(name)
    client.create_collection(
        name, vectors_config={vector_name: models.VectorParams(size=dim, distance=models.Distance.COSINE)}
    )


def build_image_index(client: QdrantClient, records: Sequence, vectors: np.ndarray, name: str = IMAGES) -> None:
    """(Re)create the image collection from records (eye_rag.rfmid.Record) and their vectors."""
    _recreate(client, name, "image", vectors.shape[1])
    client.upload_points(
        name,
        [
            models.PointStruct(
                id=i,
                vector={"image": v.tolist()},
                payload={
                    "id": r.id,
                    "split": r.split,
                    "labels": sorted(r.label_set),
                    "disease_risk": r.disease_risk,
                },
            )
            for i, (r, v) in enumerate(zip(records, vectors, strict=True))
        ],
    )


def label_texts() -> list[tuple[str, str, str, str]]:
    """(code, name, description, text to embed) for every condition plus NORMAL."""
    rows = [(c.code, c.name, c.description, f"{c.name}: {c.description}") for c in CONDITIONS]
    rows.append((NORMAL, "normal fundus", NORMAL_DESCRIPTION, f"normal fundus: {NORMAL_DESCRIPTION}"))
    return rows


def build_label_index(client: QdrantClient, vectors: np.ndarray, name: str = LABELS) -> None:
    rows = label_texts()
    _recreate(client, name, "text", vectors.shape[1])
    client.upload_points(
        name,
        [
            models.PointStruct(id=i, vector={"text": v.tolist()}, payload={"code": c, "name": n, "description": d})
            for i, ((c, n, d, _), v) in enumerate(zip(rows, vectors, strict=True))
        ],
    )


def search_images(
    client: QdrantClient, queries: np.ndarray, k: int, name: str = IMAGES
) -> tuple[np.ndarray, np.ndarray]:
    """Top-k neighbours for each query: (point ids (n, k), cosine scores (n, k))."""
    reqs = [
        models.QueryRequest(query=q.tolist(), using="image", limit=k, with_payload=False) for q in queries
    ]
    ids = np.zeros((len(queries), k), dtype=np.int64)
    scores = np.zeros((len(queries), k), dtype=np.float32)
    for start in range(0, len(reqs), 256):
        for i, res in enumerate(client.query_batch_points(name, reqs[start : start + 256]), start):
            ids[i] = [p.id for p in res.points]
            scores[i] = [p.score for p in res.points]
    return ids, scores
