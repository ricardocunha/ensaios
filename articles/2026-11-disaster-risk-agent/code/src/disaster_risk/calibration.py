"""Empirical likelihood ratios per signal band, fitted on the historical replay (TRAIN only).

Each band keeps its milestone 2 *definition* and gets LR(band) = P(band | H) / P(band | not H) from the
data, pooled across places per (role, source), with add-half smoothing. Bands with fewer than
MIN_RECORDS records keep LR 1, every LR is clipped to [LR_MIN, LR_MAX], missing signals are not counted.
Only TRAIN hours (2019-01 → 2022-12, local) are used, so 2023 and 2024 are out of sample.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from .fusion import PLACES, Place, band_key
from .signals import Signal

SMOOTHING = 0.5
MIN_RECORDS = 20
LR_MIN, LR_MAX = 0.01, 1000.0


@dataclass(frozen=True)
class BandStat:
    key: str
    n_pos: int
    n_neg: int
    lr: float


def count_bands(
    records: Iterable[tuple[str, int | None, list[Signal]]], places: dict[str, Place] = PLACES
) -> dict[str, list[int]]:
    """{band key: [n_neg, n_pos]} from (place, label, signals at that hour) records."""
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for place_name, y, signals in records:
        if y is None:
            continue
        place = places[place_name]
        for s in signals:
            if s.kind != "warning" or s.likelihood_ratio is None or s.status == "missing":
                continue
            role = place.role(s.source, s.station)
            if role is None:
                continue
            counts[band_key(role, s.source, s.likelihood_ratio)][y] += 1
    return dict(counts)


def fit_lr_table(counts: dict[str, list[int]]) -> dict[str, BandStat]:
    groups: dict[str, list[str]] = defaultdict(list)
    for k in counts:
        groups[k.rsplit("|", 1)[0]].append(k)
    out = {}
    for keys in groups.values():
        n0_all = sum(counts[k][0] for k in keys)
        n1_all = sum(counts[k][1] for k in keys)
        big_k = len(keys)
        for k in keys:
            n0, n1 = counts[k]
            if n0 + n1 < MIN_RECORDS or n1_all == 0 or n0_all == 0:
                lr = 1.0
            else:
                p1 = (n1 + SMOOTHING) / (n1_all + SMOOTHING * big_k)
                p0 = (n0 + SMOOTHING) / (n0_all + SMOOTHING * big_k)
                lr = min(LR_MAX, max(LR_MIN, p1 / p0))
            out[k] = BandStat(k, n1, n0, lr)
    return out


def as_table(stats: dict[str, BandStat]) -> dict[str, float]:
    return {k: v.lr for k, v in stats.items()}
