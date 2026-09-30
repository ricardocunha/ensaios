"""Rolling rain accumulations → likelihood ratio (shared by ANA gauge rain and INMET).

Rule (fixed, the same for every station; chosen as round numbers before the
backtest, to be calibrated in milestone 3):

    LR 10  if 24 h >= 150 mm or 72 h >= 300 mm
    LR  5  if 24 h >= 100 mm or 72 h >= 200 mm
    LR  2  if 24 h >=  50 mm or 72 h >= 100 mm
    LR 0.5 if 72 h <   20 mm (dry: evidence against)
    LR  1  otherwise

Accumulations only sum readings that exist. ``coverage`` (readings received /
readings expected over 72 h) scales reliability, because a sum with holes is a
lower bound: a high value is still real evidence, a low one may be an artefact.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from ..dataset import HourRow
from . import Signal, age_hours, missing, staleness

BANDS = [  # (lr, min 24 h mm, min 72 h mm)
    (10.0, 150.0, 300.0),
    (5.0, 100.0, 200.0),
    (2.0, 50.0, 100.0),
]
DRY_72H_MM = 20.0
DRY_LR = 0.5


def rain_lr(acc24: float, acc72: float) -> tuple[float, str]:
    for lr, a24, a72 in BANDS:
        if acc24 >= a24 or acc72 >= a72:
            return lr, f"24h {acc24:.1f} mm >= {a24:g} or 72h {acc72:.1f} mm >= {a72:g}"
    if acc72 < DRY_72H_MM:
        return DRY_LR, f"72h {acc72:.1f} mm < {DRY_72H_MM:g} (dry)"
    return 1.0, f"24h {acc24:.1f} mm, 72h {acc72:.1f} mm: below every band"


def rain_signal(
    source: str, station: str, place: str, t: datetime, rows: Sequence[HourRow], base_reliability: float
) -> Signal:
    """Signal from the rows available at ``t`` (only the last 72 h are used)."""
    lo72, lo24 = t - timedelta(hours=72), t - timedelta(hours=24)
    win = [r for r in rows[-80:] if lo72 < r.hour_end <= t]
    got72 = sum(r.rain_n for r in win)
    if got72 == 0:
        return missing(source, station, place, t, "mm", "no rain reading in the last 72 h")
    exp72 = 72 * (win[-1].n_expected if win else 1)
    acc72 = sum(r.rain_mm for r in win if r.rain_mm is not None)
    acc24 = sum(r.rain_mm for r in win if r.rain_mm is not None and r.hour_end > lo24)
    coverage = min(1.0, got72 / exp72)
    last = rows[-1].rain_last_time
    age = age_hours(t, last)
    status, stale_mult = staleness(age)
    lr, why = rain_lr(acc24, acc72)
    return Signal(
        source=source,
        station=station,
        place=place,
        time=t,
        observed_at=last,
        value=round(acc24, 1),
        unit="mm/24h",
        likelihood_ratio=lr,
        freshness_h=age,
        reliability=round(base_reliability * coverage * stale_mult, 4),
        status=status,
        reason=why,
        details={"acc24_mm": round(acc24, 1), "acc72_mm": round(acc72, 1), "coverage72": round(coverage, 3)},
    )
