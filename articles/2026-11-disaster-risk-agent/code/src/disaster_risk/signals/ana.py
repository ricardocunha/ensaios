"""ANA telemetry adapter: river level (per-station thresholds) and gauge rain.

Level rule (per station, explicit):

    thresholds: p90, p99 of the station's own 2019-01 → 2024-04-19 record
                (see thresholds.py) and the official flood level when one is
                known (basin.FLOOD_LEVEL_CM); without an official level, the
                historical p99.9 takes its place.

    LR 10  level >= flood level (or p99.9)
    LR  4  level >= p99
    LR 1.5 level >= p90
    LR 0.5 below p90
    x2     if the level rose >= 100 cm over the 6 h before the reading (capped at 20)

The level used is the latest real reading available at ``t``, however old; its
age goes into ``freshness_h`` and lowers ``reliability`` (see signals.staleness).
A station with no historical record (Usina do Gasômetro started reporting on
2024-05-03) gets LR 1: we do not know what its numbers mean.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from .. import basin
from ..dataset import HourRow
from ..observations import Snapshot
from ..thresholds import LevelThresholds
from . import MAX_AGE_H, Signal, _rain, age_hours, missing, staleness

LEVEL_RELIABILITY = 0.9
RAIN_RELIABILITY = 0.8
RISE_WINDOW = timedelta(hours=6)
RISE_TOLERANCE = timedelta(hours=1)  # the reading ~6 h earlier may be up to 1 h off
RISE_CM = 100.0
RISE_FACTOR = 2.0
LR_CAP = 20.0


def level_bands(th: LevelThresholds | None, flood_cm: float | None) -> list[tuple[float, float, str]]:
    """[(min level cm, LR, label)] from the highest band down."""
    if th is None and flood_cm is None:
        return []
    bands = []
    if flood_cm is not None:
        bands.append((flood_cm, 10.0, "flood level"))
    elif th is not None:
        bands.append((th.p999, 10.0, "p99.9"))
    if th is not None:
        bands += [(th.p99, 4.0, "p99"), (th.p90, 1.5, "p90")]
    return sorted(bands, key=lambda b: -b[0])


def level_lr(level: float, bands: list[tuple[float, float, str]]) -> tuple[float, str]:
    if not bands:
        return 1.0, "no historical record or official level for this gauge"
    for lo, lr, label in bands:
        if level >= lo:
            return lr, f"level {level:g} cm >= {label} {lo:g}"
    lo, _, label = bands[-1]
    return 0.5, f"level {level:g} cm < {label} {lo:g}"


def _last_level(rows: Sequence[HourRow]) -> HourRow | None:
    for r in reversed(rows[-int(MAX_AGE_H) - 2 :]):
        if r.level_cm is not None:
            return r
    return None


def _level_before(rows: Sequence[HourRow], when: datetime) -> HourRow | None:
    """Latest row with a level reading at or before ``when`` (within tolerance)."""
    for r in reversed(rows[-int(MAX_AGE_H) - 2 :]):
        if r.level_cm is not None and r.level_time <= when:
            return r if when - r.level_time <= RISE_TOLERANCE else None
    return None


def level_signal(
    station: str, t: datetime, rows: Sequence[HourRow], th: LevelThresholds | None, flood_cm: float | None
) -> Signal:
    place = basin.STATION_PLACE.get(station, "")
    last = _last_level(rows)
    if last is None:
        return missing("ana_level", station, place, t, "cm", f"no level reading in the last {MAX_AGE_H:g} h")
    age = age_hours(t, last.level_time)
    status, stale_mult = staleness(age)
    if status == "missing":
        return missing("ana_level", station, place, t, "cm", f"latest level is {age:.1f} h old")
    lr, why = level_lr(last.level_cm, level_bands(th, flood_cm))
    details: dict = {}
    before = _level_before(rows, last.level_time - RISE_WINDOW)
    if before is not None:
        rise = last.level_cm - before.level_cm
        details["rise_6h_cm"] = rise
        # The rise bonus only applies where the level itself is interpretable.
        if rise >= RISE_CM and level_bands(th, flood_cm):
            lr = min(LR_CAP, lr * RISE_FACTOR)
            why += f"; rose {rise:g} cm in 6 h (x{RISE_FACTOR:g})"
    return Signal(
        source="ana_level",
        station=station,
        place=place,
        time=t,
        observed_at=last.level_time,
        value=last.level_cm,
        unit="cm",
        likelihood_ratio=lr,
        freshness_h=age,
        reliability=round(LEVEL_RELIABILITY * stale_mult, 4),
        status=status,
        reason=why,
        details=details,
    )


class AnaAdapter:
    """Emits one level signal and one gauge-rain signal per ANA station per step."""

    name = "ana"

    def __init__(self, thresholds: dict[str, LevelThresholds], flood_levels: dict[str, float] | None = None):
        self.thresholds = thresholds
        self.flood_levels = basin.FLOOD_LEVEL_CM if flood_levels is None else flood_levels

    def emit(self, snap: Snapshot) -> list[Signal]:
        out = []
        for station in snap.stations("ana"):
            rows = snap.rows("ana", station)
            place = basin.STATION_PLACE.get(station, "")
            if not rows:
                out.append(missing("ana_level", station, place, snap.t, "cm", "no data yet"))
                out.append(missing("ana_rain", station, place, snap.t, "mm", "no data yet"))
                continue
            out.append(level_signal(station, snap.t, rows, self.thresholds.get(station), self.flood_levels.get(station)))
            out.append(_rain.rain_signal("ana_rain", station, place, snap.t, rows, RAIN_RELIABILITY))
        return out
