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


def test_m4_macro_f1_skips_conditions_absent_from_a_resample():
    from eye_rag.m4 import bootstrap, interval, macro_f1_present

    y = np.array([[1, 0], [1, 0], [0, 0]], dtype=bool)
    p = np.array([[1, 0], [0, 0], [0, 0]], dtype=bool)
    assert macro_f1_present(y, p, [0, 1]) == 2 / 3  # column 1 has no positives: left out, not scored 1
    d = bootstrap(3, lambda i: float(i.mean()), b=200)
    assert d.shape == (200,) and (d == bootstrap(3, lambda i: float(i.mean()), b=200)).all()
    r = interval(0.5, d)
    assert r["point"] == 0.5 and r["ci95"][0] <= r["ci95"][1]
