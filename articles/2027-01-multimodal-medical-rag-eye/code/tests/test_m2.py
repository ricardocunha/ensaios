import numpy as np

from eye_rag.diagnose import subset
from eye_rag.m2 import COLUMNS, vlm_matrix


def test_vlm_matrix_marks_labels_risk_and_failures():
    rows = [{"id": "test/1", "labels": ["DR", "MH"]}, {"id": "test/2", "labels": ["normal"]}, {"id": "test/3", "labels": None}]
    ids, P, failed = vlm_matrix(rows)
    assert ids == ["test/1", "test/2", "test/3"] and failed == 1
    assert P[0, 0] and P[0, COLUMNS.index("DR")] and P[0, COLUMNS.index("MH")] and P[0].sum() == 3
    assert not P[1].any() and not P[2].any()


def test_subset_is_seeded_and_skips_exclusions():
    ids = [f"test/{i}" for i in range(1, 21)]
    a = subset(ids, frozenset({"test/3"}), 5)
    assert a == subset(ids, frozenset({"test/3"}), 5) and len(a) == 5 and "test/3" not in a
    assert len(subset(ids, frozenset({"test/3"}), None)) == 19
    assert np.unique(a).size == 5
