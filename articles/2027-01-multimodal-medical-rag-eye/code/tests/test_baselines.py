import numpy as np
import pytest

from eye_rag import baselines as B


def test_knn_majority_and_weighted_scores():
    # one query, 3 neighbours, 2 labels
    ynb = np.array([[[1, 0], [1, 1], [0, 1]]])
    sims = np.array([[0.9, 0.6, 0.3]])
    assert B.knn_scores(ynb, sims, 3, weighted=False)[0] == pytest.approx([2 / 3, 2 / 3])
    assert B.knn_scores(ynb, sims, 3)[0] == pytest.approx([1.5 / 1.8, 0.9 / 1.8])
    assert B.knn_scores(ynb, sims, 1)[0] == pytest.approx([1.0, 0.0])


def test_tune_knn_finds_the_perfect_setting():
    # label 0 is carried by the first neighbour only: k=1 is perfect
    y_val = np.array([[1], [0]])
    ynb = np.array([[[1], [0], [0]], [[0], [1], [1]]])
    sims = np.ones((2, 3))
    c = B.tune_knn(y_val, ynb, sims, [0], ks=(1, 3), thresholds=(0.5,))
    assert (c.k, c.threshold, c.val_macro_f1) == (1, 0.5, pytest.approx(1.0))


def test_prompt_vectors_average_and_normalise():
    tv = np.array([[1.0, 0], [0, 1.0], [1.0, 0], [1.0, 0]])  # 2 classes x 2 templates
    pv = B.prompt_vectors(tv, 2)
    assert pv.shape == (2, 2)
    assert np.linalg.norm(pv, axis=1) == pytest.approx([1, 1])
    assert pv[1] == pytest.approx([1, 0])


def test_zero_shot_probs_two_way_softmax():
    img = np.array([[1.0, 0.0]])
    pos = np.array([[1.0, 0.0], [0.0, 1.0]])
    neg = np.array([0.0, 1.0])
    p = B.zero_shot_probs(img, pos, neg, logit_scale=10)
    assert p[0, 0] == pytest.approx(1 / (1 + np.exp(-10)))
    assert p[0, 1] == pytest.approx(0.5)


def test_tune_thresholds_per_label():
    y = np.array([[1, 0], [1, 0], [0, 0]])
    s = np.array([[0.9, 0.1], [0.7, 0.2], [0.8, 0.3]])
    thr = B.tune_thresholds_per_label(y, s)
    assert thr[0] == pytest.approx(0.7)  # >= 0.7 catches both positives (F1 0.8)
    assert thr[1] == 0.5  # no positives: default
