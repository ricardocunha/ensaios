"""Signal adapters: one module per source, all emitting :class:`Signal`.

A signal is evidence about one hypothesis, "flood risk is elevated here", as a likelihood ratio
(LR > 1 pushes towards an alert, LR < 1 away from it, LR = 1 says nothing). Freshness and reliability
are separate from the LR on purpose; nothing is interpolated. Adapters take a
:class:`~disaster_risk.observations.Snapshot` and cannot see anything after its time ``t``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from ..observations import Snapshot

# Staleness: reliability halves every STALE_HALF_LIFE_H hours once the latest reading is more than
# FRESH_H old. After MAX_AGE_H the reading is dropped (status "missing", LR 1, reliability 0).
FRESH_H = 1.0
STALE_HALF_LIFE_H = 6.0
MAX_AGE_H = 72.0


@dataclass(frozen=True)
class Signal:
    source: str  # "ana_level" | "ana_rain" | "inmet_rain" | "copernicus_ems"
    station: str  # station code or EMS product id
    place: str  # municipality (gauges, INMET) or AOI name (EMS)
    time: datetime  # UTC: when the signal is emitted (the replay clock)
    observed_at: datetime | None  # UTC time of the latest reading behind the value
    value: float | None  # level cm, rain mm, flooded ha, ...
    unit: str
    likelihood_ratio: float | None  # None for label signals (not evidence for warning)
    freshness_h: float | None  # time - observed_at, hours
    reliability: float  # 0..1: how much fusion should trust this LR now
    status: str  # "fresh" | "stale" | "missing"
    kind: str = "warning"  # "warning" (input to fusion) | "label" (post-event confirmation)
    reason: str = ""  # human-readable: which rule produced the LR
    details: dict = field(default_factory=dict)


class Adapter(Protocol):
    name: str

    def emit(self, snap: Snapshot) -> list[Signal]: ...


def age_hours(t: datetime, observed_at: datetime | None) -> float | None:
    return None if observed_at is None else (t - observed_at).total_seconds() / 3600


def staleness(age_h: float | None) -> tuple[str, float]:
    """(status, multiplier for reliability) for a reading of this age."""
    if age_h is None or age_h > MAX_AGE_H:
        return "missing", 0.0
    if age_h <= FRESH_H:
        return "fresh", 1.0
    return "stale", 0.5 ** ((age_h - FRESH_H) / STALE_HALF_LIFE_H)


def missing(source: str, station: str, place: str, t: datetime, unit: str, why: str) -> Signal:
    """An explicit "no usable data" signal: neutral LR, zero reliability."""
    return Signal(source, station, place, t, None, None, unit, 1.0, None, 0.0, "missing", reason=why)
