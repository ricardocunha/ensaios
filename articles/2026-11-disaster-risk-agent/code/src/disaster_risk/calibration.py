"""Empirical likelihood ratios per signal band, fitted on the historical replay (TRAIN only).

The milestone 2 rules give each band a round-number LR (level at the flood
level: 10; 24 h rain >= 150 mm: 10; ...). Those numbers were never checked
against the record, and with priors of 0.3–1.3 % they cannot move the fused
probability far enough (RESULTS.md, "hand-set LRs"). Here each band keeps its
*definition* and gets its LR from the data:

    LR(band) = P(band | H) / P(band | not H)
             = ((n1 + a) / (N1 + a K)) / ((n0 + a) / (N0 + a K))

per group g = (role, source), pooled across places (a gauge's bands are
already relative to its own history, so "own gauge at p99" means the same
thing at Muçum and at Taquari). n1 / n0: (place, hour) records in the band
with H = 1 / 0; N1 / N0: all records of the group; K: bands seen in the group;
a = 0.5 (add-half smoothing). Bands with fewer than MIN_RECORDS records keep
LR 1 (not enough data to say anything), and every LR is clipped to
[LR_MIN, LR_MAX]. Missing signals are not counted (their LR stays 1).

Only TRAIN hours (2019-01 → 2022-12, local) are used, so the 2023 floods
(September, November) and 2024 are out of sample.
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
