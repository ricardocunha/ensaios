import numpy as np
import pytest

from eye_rag.metrics import any_overlap_precision_at_k, f1_per_label, label_precision_at_k, macro_f1


def test_f1_per_label_hand_computed():
    y = np.array([[1, 0], [1, 1], [0, 1], [0, 0]])
    p = np.array([[1, 0], [0, 1], [1, 1], [0, 1]])
    # label 0: tp1 fp1 fn1 -> 0.5 ; label 1: tp2 fp1 fn0 -> 0.8
    assert f1_per_label(y, p) == pytest.approx([0.5, 0.8])


def test_macro_f1_skips_labels_without_positives_by_default():
    y = np.array([[1, 0], [0, 0]])
    p = np.array([[1, 1], [0, 0]])
    assert macro_f1(y, p) == pytest.approx(1.0)  # only label 0 counts
    assert macro_f1(y, p, [0, 1]) == pytest.approx(0.5)  # label 1: tp0 fp1 -> 0


def test_any_overlap_precision_at_k():
    q = [frozenset({"A"}), frozenset({"B", "C"})]
    nb = [[frozenset({"A"}), frozenset({"B"})], [frozenset({"C"}), frozenset({"C", "A"})]]
    assert any_overlap_precision_at_k(q, nb, 1) == pytest.approx(1.0)
    assert any_overlap_precision_at_k(q, nb, 2) == pytest.approx((0.5 + 1.0) / 2)


def test_label_precision_at_k_and_nan_for_absent_label():
    yq = np.array([[1, 0], [1, 0], [0, 0]])
    ynb = np.array([[[1, 0], [0, 0]], [[1, 0], [1, 0]], [[1, 1], [1, 1]]])
    out = label_precision_at_k(yq, ynb, 2)
    assert out[0] == pytest.approx(0.75) and np.isnan(out[1])
