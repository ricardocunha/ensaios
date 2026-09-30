"""Labels for scoring fusion: did the gauge reach its flood level soon after ``t``?

    H(gauge, t) = 1  if any 15-min level reading in (t - 1 h, t + HORIZON] is >= the flood level
                = 0  if none is, and the window has at least MIN_COVERAGE of its expected readings
                = None (unknown) otherwise: a silent gauge cannot give a negative label

Labels look into the future by definition. They are used only to *score*
(priors from history, Brier score, false alarms), never as input to a signal.

The prior for a place is the share of labelled TRAIN hours with H = 1
(ANA record 2019-01-01 → 2022-12-31 local; 2023 and 2024 stay out of sample),
with add-one smoothing: (positives + 1) / (labelled + 2).
"""

from __future__ import annotations

import json
from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import basin
from .sources._http import DATA_DIR

HORIZON = timedelta(hours=24)
LOOKBACK = timedelta(hours=1)
MIN_COVERAGE = 0.5
READINGS_PER_HOUR = 4
NEW_FLOOD_GAP = timedelta(days=7)  # a crossing counts as a new flood onset after 7 days below the flood level


@dataclass(frozen=True)
class LevelSeries:
    """Level readings of one gauge in UTC, sorted, with a prefix count of readings >= flood level."""

    times: list[datetime]
    levels: list[float]
    flood_cm: float
    _above: list[int]

    @classmethod
    def from_readings(cls, readings, flood_cm: float) -> LevelSeries:
        pts = sorted(
            ((r.time - basin.ANA_UTC_OFFSET).replace(tzinfo=timezone.utc), r.level_cm)
            for r in readings if r.level_cm is not None
        )
        above = [0]
        for _, lv in pts:
            above.append(above[-1] + (lv >= flood_cm))
        return cls([t for t, _ in pts], [lv for _, lv in pts], flood_cm, above)

    def _span(self, lo: datetime, hi: datetime) -> tuple[int, int]:
        """Index range of readings in (lo, hi]."""
        return bisect_right(self.times, lo), bisect_right(self.times, hi)

    def any_above(self, lo: datetime, hi: datetime) -> bool:
        i, j = self._span(lo, hi)
        return self._above[j] - self._above[i] > 0

    def count(self, lo: datetime, hi: datetime) -> int:
        i, j = self._span(lo, hi)
        return j - i

    def max_level(self, lo: datetime, hi: datetime) -> float | None:
        i, j = self._span(lo, hi)
        return max(self.levels[i:j]) if j > i else None

    def label(self, t: datetime, horizon: timedelta = HORIZON) -> int | None:
        lo, hi = t - LOOKBACK, t + horizon
        if self.any_above(lo, hi):
            return 1
        expected = (hi - lo).total_seconds() / 3600 * READINGS_PER_HOUR
        return 0 if self.count(lo, hi) >= MIN_COVERAGE * expected else None

    def first_at_or_above(self, lo: datetime, hi: datetime) -> datetime | None:
        i, j = self._span(lo, hi)
        for k in range(i, j):
            if self.levels[k] >= self.flood_cm:
                return self.times[k]
        return None

    def flood_onsets(self, lo: datetime, hi: datetime, gap: timedelta = NEW_FLOOD_GAP) -> list[datetime]:
        """Readings >= flood level in (lo, hi] with no reading >= flood level in the ``gap`` before."""
        out = []
        i, j = self._span(lo, hi)
        last_above = None
        # seed with the latest above-flood reading before lo (within gap)
        k0 = bisect_left(self.times, lo - gap)
        for k in range(k0, i):
            if self.levels[k] >= self.flood_cm:
                last_above = self.times[k]
        for k in range(i, j):
            if self.levels[k] >= self.flood_cm:
                if last_above is None or self.times[k] - last_above > gap:
                    out.append(self.times[k])
                last_above = self.times[k]
        return out


def labels_for(series: LevelSeries, hours: Sequence[datetime]) -> list[int | None]:
    return [series.label(t) for t in hours]


def historical_prior(series: LevelSeries, start: datetime, end: datetime) -> tuple[float, int, int]:
    """(smoothed prior, positives, labelled hours) over hourly steps in (start, end]."""
    pos = n = 0
    t = start + timedelta(hours=1)
    while t <= end:
        y = series.label(t)
        if y is not None:
            n += 1
            pos += y
        t += timedelta(hours=1)
    return (pos + 1) / (n + 2), pos, n


# History used for priors: the TRAIN years (2019-2022, local), in UTC.
PRIOR_START = datetime(2019, 1, 1, 3, tzinfo=timezone.utc)
PRIOR_END = datetime(2023, 1, 1, 3, tzinfo=timezone.utc)


def cache_path(data_dir: Path = DATA_DIR) -> Path:
    return data_dir / "cache" / "priors_train.json"


def load_or_compute_priors(series_by_place: dict[str, LevelSeries], data_dir: Path = DATA_DIR,
                           *, rebuild: bool = False) -> dict[str, dict]:
    """{place: {"prior", "positives", "labelled"}} from the historical record (cached)."""
    path = cache_path(data_dir)
    if path.exists() and not rebuild:
        cached = json.loads(path.read_text())
        if set(cached) == set(series_by_place):
            return cached
    out = {}
    for place, s in series_by_place.items():
        p, pos, n = historical_prior(s, PRIOR_START, PRIOR_END)
        out[place] = {"prior": p, "positives": pos, "labelled": n}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return out
