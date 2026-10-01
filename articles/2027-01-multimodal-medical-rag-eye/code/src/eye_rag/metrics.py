"""Multi-label metrics: per-label F1, macro-F1, and retrieval label precision@k."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def f1_per_label(y_true: np.ndarray, y_pred: np.ndarray) -> np.ndarray:
    """F1 per column. A label with no positives and no predictions scores 1 by convention;
    callers should only average over labels that have positives in `y_true`."""
    y_true = y_true.astype(bool)
    y_pred = y_pred.astype(bool)
    tp = (y_true & y_pred).sum(0)
    fp = (~y_true & y_pred).sum(0)
    fn = (y_true & ~y_pred).sum(0)
    denom = 2 * tp + fp + fn
    return np.where(denom == 0, 1.0, 2 * tp / np.maximum(denom, 1))


def macro_f1(y_true: np.ndarray, y_pred: np.ndarray, columns: Sequence[int] | None = None) -> float:
    """Mean F1 over `columns` (default: every column with at least one positive)."""
    if columns is None:
        columns = np.flatnonzero(y_true.sum(0) > 0)
    return float(f1_per_label(y_true[:, columns], y_pred[:, columns]).mean())


def any_overlap_precision_at_k(query_sets: Sequence[frozenset], neighbour_sets: Sequence[Sequence[frozenset]], k: int) -> float:
    """Mean over queries of the share of the top-k neighbours that share >= 1 label with the query."""
    vals = [np.mean([bool(q & n) for n in ns[:k]]) for q, ns in zip(query_sets, neighbour_sets, strict=True)]
    return float(np.mean(vals))


def label_precision_at_k(y_query: np.ndarray, y_neighbours: np.ndarray, k: int) -> np.ndarray:
    """Per label c: over queries positive for c, the mean share of the top-k neighbours
    also positive for c. y_neighbours has shape (n_queries, >=k, n_labels). NaN for labels
    with no positive query."""
    share = y_neighbours[:, :k, :].mean(axis=1)  # (n, L)
    pos = y_query.astype(bool)
    with np.errstate(invalid="ignore"):
        return np.where(pos.sum(0) > 0, (share * pos).sum(0) / pos.sum(0), np.nan)
