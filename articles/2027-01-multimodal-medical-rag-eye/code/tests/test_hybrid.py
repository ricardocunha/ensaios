from pathlib import Path

import numpy as np

from conftest import make_csv
from eye_rag.embed import normalize
from eye_rag.hybrid import Vocabulary, build_hybrid_index, query_text_from_labels, search, tokenize
from eye_rag.index import open_client
from eye_rag.rfmid import parse_labels_csv


def test_tokenize_and_sparse_counts():
    assert tokenize("Diabetic retinopathy (DR): microaneurysms and the hemorrhages") == ["diabetic", "retinopathy", "dr", "microaneurysms", "hemorrhages"]
    v = Vocabulary(["red red disc", "pale disc"])
    s = v.sparse("red disc unknown red")
    assert dict(zip(s.indices, s.values)) == {v.index["red"]: 2.0, v.index["disc"]: 1.0}


def _index(n=40, d=8):
    labels = [{"DR"} if i % 4 == 0 else ({"MYA"} if i % 4 == 1 else set()) for i in range(n)]
    recs = parse_labels_csv(make_csv(list(enumerate(labels))), "train", Path("x"))
    vecs = normalize(np.random.default_rng(0).normal(size=(n, d)).astype(np.float32))
    client = open_client(":memory:")
    return client, build_hybrid_index(client, recs, vecs), recs, vecs


def test_dense_only_matches_bruteforce():
    client, vocab, _, vecs = _index()
    q = normalize(np.random.default_rng(1).normal(size=(3, vecs.shape[1])).astype(np.float32))
    ids = search(client, vocab, q, None, 5)
    assert (ids == np.argsort(-(q @ vecs.T), axis=1)[:, :5]).all()


def test_hybrid_text_pulls_matching_reports_up():
    client, vocab, recs, vecs = _index()
    q = normalize(np.random.default_rng(2).normal(size=(1, vecs.shape[1])).astype(np.float32))
    dense = search(client, vocab, q, None, 10)[0]
    hyb = search(client, vocab, q, [query_text_from_labels(["MYA"])], 10)[0]
    share = lambda ids: np.mean(["MYA" in recs[i].labels for i in ids])
    assert share(hyb) > share(dense)
    # empty query text falls back to dense
    assert (search(client, vocab, q, [""], 10)[0] == dense).all()
