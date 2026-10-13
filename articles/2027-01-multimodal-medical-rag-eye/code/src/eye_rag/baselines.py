"""The two Milestone 1 baselines, as pure functions on arrays.

(a) kNN: the (similarity-weighted) share of the top-k training neighbours with the label.
(b) Zero-shot BiomedCLIP: per label, "fundus with <label>" vs "normal fundus" prompts.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from eye_rag.metrics import macro_f1


def knn_scores(y_neighbours: np.ndarray, sims: np.ndarray, k: int, weighted: bool = True) -> np.ndarray:
    """y_neighbours: (n, >=k, L) 0/1 labels of the ranked neighbours; sims: (n, >=k).
    Returns (n, L) scores in [0, 1]."""
    y = y_neighbours[:, :k, :].astype(np.float32)
    if not weighted:
        return y.mean(axis=1)
    w = np.clip(sims[:, :k], 0, None).astype(np.float32)
    w = w / np.maximum(w.sum(axis=1, keepdims=True), 1e-12)
    return np.einsum("nk,nkl->nl", w, y)


@dataclass(frozen=True)
class KnnChoice:
    k: int
    threshold: float
    val_macro_f1: float


def tune_knn(
    y_val: np.ndarray,
    y_neighbours_val: np.ndarray,
    sims_val: np.ndarray,
    columns: Sequence[int],
    ks: Sequence[int] = (1, 3, 5, 10, 20, 30, 50),
    thresholds: Sequence[float] = tuple(np.round(np.arange(0.05, 0.65, 0.05), 2)),
) -> KnnChoice:
    """Pick (k, one global threshold) maximising validation macro-F1 over `columns`.
    Ties go to the smaller k, then the higher threshold (grid order)."""
    best: KnnChoice | None = None
    for k in ks:
        s = knn_scores(y_neighbours_val, sims_val, k)
        for t in sorted(thresholds, reverse=True):
            f = macro_f1(y_val, s >= t, columns)
            if best is None or f > best.val_macro_f1 + 1e-12:
                best = KnnChoice(k, float(t), f)
    assert best is not None
    return best


def prompt_vectors(text_vectors: np.ndarray, n_templates: int) -> np.ndarray:
    """Average the template embeddings of each class (rows grouped per class), re-normalised."""
    v = text_vectors.reshape(-1, n_templates, text_vectors.shape[-1]).mean(axis=1)
    return v / np.linalg.norm(v, axis=-1, keepdims=True)


def zero_shot_probs(image_vectors: np.ndarray, positive: np.ndarray, negative: np.ndarray, logit_scale: float) -> np.ndarray:
    """p(label) = softmax over {positive_label, negative} of logit_scale * cosine.
    image_vectors (n, d), positive (L, d), negative (d,). Returns (n, L)."""
    s_pos = image_vectors @ positive.T
    s_neg = image_vectors @ negative
    return 1.0 / (1.0 + np.exp(-logit_scale * (s_pos - s_neg[:, None])))


def tune_thresholds_per_label(y_val: np.ndarray, scores_val: np.ndarray) -> np.ndarray:
    """Per label, the threshold (among the observed validation scores) that maximises
    validation F1. Labels without validation positives keep 0.5."""
    from eye_rag.metrics import f1_per_label

    out = np.full(y_val.shape[1], 0.5)
    for j in range(y_val.shape[1]):
        if y_val[:, j].sum() == 0:
            continue
        cands = np.unique(scores_val[:, j])
        f = [f1_per_label(y_val[:, [j]], (scores_val[:, [j]] >= t))[0] for t in cands]
        out[j] = cands[int(np.argmax(f))]
    return out
