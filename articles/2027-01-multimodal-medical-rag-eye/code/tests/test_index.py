from pathlib import Path

import numpy as np

from conftest import make_csv
from eye_rag.embed import cached, normalize
from eye_rag.index import IMAGES, LABELS, build_image_index, build_label_index, label_texts, open_client, search_images
from eye_rag.labels import NORMAL
from eye_rag.rfmid import parse_labels_csv


def _fixture(n=30, d=16, seed=0):
    rng = np.random.default_rng(seed)
    recs = parse_labels_csv(make_csv([(i, {"DR"} if i % 3 else set()) for i in range(n)]), "train", Path("x"))
    return recs, normalize(rng.normal(size=(n, d)).astype(np.float32))


def test_qdrant_search_matches_bruteforce_cosine():
    recs, vecs = _fixture()
    client = open_client(":memory:")
    build_image_index(client, recs, vecs)
    q = normalize(np.random.default_rng(1).normal(size=(5, vecs.shape[1])).astype(np.float32))
    ids, scores = search_images(client, q, k=4)
    expected = np.argsort(-(q @ vecs.T), axis=1)[:, :4]
    assert (ids == expected).all()
    assert np.allclose(scores, np.take_along_axis(q @ vecs.T, expected, axis=1), atol=1e-5)


def test_image_payload_holds_labels_and_normal():
    recs, vecs = _fixture(n=3)
    client = open_client(":memory:")
    build_image_index(client, recs, vecs)
    pts = {p.payload["id"]: p.payload for p in client.scroll(IMAGES, limit=10)[0]}
    assert pts["train/0"]["labels"] == [NORMAL] and pts["train/0"]["disease_risk"] == 0
    assert pts["train/1"]["labels"] == ["DR"]


def test_label_index_has_one_point_per_condition_plus_normal():
    rows = label_texts()
    client = open_client(":memory:")
    build_label_index(client, normalize(np.random.default_rng(0).normal(size=(len(rows), 8))))
    assert client.count(LABELS).count == len(rows) == 46


def test_cache_reuses_and_invalidates(tmp_path):
    calls = []

    def compute():
        calls.append(1)
        return np.ones((2, 3))

    cached("x", ["a", "b"], compute, tmp_path)
    cached("x", ["a", "b"], compute, tmp_path)
    assert len(calls) == 1
    cached("x", ["a", "c"], compute, tmp_path)  # different ids -> recompute
    cached("x", ["a", "c"], compute, tmp_path, meta={"v": 2})  # different meta -> recompute
    assert len(calls) == 3
