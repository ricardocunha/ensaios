"""Backtest harness (skeleton): replay the dataset hour by hour, emit signals.

At each step ``t`` every adapter receives ``store.as_of(t)`` and nothing else,
so a reading is usable only once it is available (see observations.py).
This module reports when each signal first crossed a likelihood-ratio level and
how stale the gauges were; fusion, lead times and false alarms are in
``fusion.py`` and ``evaluate.py`` (milestone 3).

``uv run python -m disaster_risk.backtest`` runs the full 2024-04-20 → 05-20
window and writes every signal to ``runs/signals.csv`` (git-ignored).
"""

from __future__ import annotations

import csv
import json
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from . import basin, dataset, thresholds
from .observations import Store
from .signals import Adapter, Signal
from .signals.ana import AnaAdapter
from .signals.copernicus_ems import CopernicusEmsAdapter
from .signals.inmet import InmetAdapter
from .sources import copernicus_ems

RUNS_DIR = Path(__file__).resolve().parents[2] / "runs"


@dataclass(frozen=True)
class Step:
    t: datetime
    signals: list[Signal]


def replay(
    store: Store, adapters: Sequence[Adapter], start: datetime, end: datetime, step: timedelta = timedelta(hours=1)
) -> Iterator[Step]:
    """Yield the signals available at each ``t`` in ``(start, end]``."""
    t = start + step
    while t <= end:
        snap = store.as_of(t)
        yield Step(t, [s for a in adapters for s in a.emit(snap)])
        t += step


def default_adapters(th: dict[str, thresholds.LevelThresholds]) -> list[Adapter]:
    return [AnaAdapter(th), InmetAdapter(), CopernicusEmsAdapter()]


# --- Reporting -------------------------------------------------------------------


def first_crossings(steps: Sequence[Step], levels: Sequence[float] = (4.0, 10.0)) -> dict[tuple[str, str], dict]:
    """Per (source, station): first replay time with LR >= each level (warning signals only)."""
    out: dict[tuple[str, str], dict] = {}
    for st in steps:
        for s in st.signals:
            if s.kind != "warning":
                continue
            d = out.setdefault((s.source, s.station), {lv: None for lv in levels} | {"place": s.place})
            for lv in levels:
                if d[lv] is None and s.likelihood_ratio is not None and s.likelihood_ratio >= lv:
                    d[lv] = st.t
    return out


def staleness_summary(steps: Sequence[Step], lo: datetime, hi: datetime) -> dict[tuple[str, str], dict]:
    """Per level/rain signal: hours fresh/stale/missing and max age within (lo, hi]."""
    out: dict[tuple[str, str], dict] = {}
    for st in steps:
        if not (lo < st.t <= hi):
            continue
        for s in st.signals:
            if s.kind != "warning":
                continue
            d = out.setdefault((s.source, s.station), {"fresh": 0, "stale": 0, "missing": 0, "max_age_h": 0.0})
            d[s.status] += 1
            if s.freshness_h is not None:
                d["max_age_h"] = max(d["max_age_h"], s.freshness_h)
    return out


def write_signals(steps: Sequence[Step], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["time", "source", "station", "place", "kind", "status", "value", "unit", "likelihood_ratio",
            "freshness_h", "reliability", "observed_at", "reason", "details"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for st in steps:
            for s in st.signals:
                w.writerow([
                    f"{s.time:%Y-%m-%dT%H:%MZ}", s.source, s.station, s.place, s.kind, s.status,
                    "" if s.value is None else s.value, s.unit,
                    "" if s.likelihood_ratio is None else s.likelihood_ratio,
                    "" if s.freshness_h is None else round(s.freshness_h, 2), s.reliability,
                    "" if s.observed_at is None else f"{s.observed_at:%Y-%m-%dT%H:%MZ}", s.reason,
                    json.dumps(s.details, ensure_ascii=False, default=str),
                ])
    return path


def _fmt(t: datetime | None) -> str:
    if t is None:
        return "never"
    local = t + basin.ANA_UTC_OFFSET
    return f"{t:%m-%d %H:%M}Z ({local:%m-%d %H:%M} local)"


def main(argv: list[str] | None = None) -> int:
    rows = dataset.load_or_build()
    th = thresholds.load_or_compute()
    products = copernicus_ems.list_products(basin.EMS_ACTIVATION)
    store = Store(rows, products)
    steps = list(replay(store, default_adapters(th), basin.WINDOW_START_UTC, basin.WINDOW_END_UTC))
    n = sum(len(s.signals) for s in steps)
    path = write_signals(steps, RUNS_DIR / "signals.csv")
    print(f"steps={len(steps)} signals={n} -> {path}")

    print("-- first replay hour with LR >= 4 / LR >= 10 (warning signals)")
    for (src, stn), d in sorted(first_crossings(steps).items()):
        print(f"{src:11} {stn:9} {d['place']:16} LR>=4: {_fmt(d[4.0])}  LR>=10: {_fmt(d[10.0])}")

    lo, hi = datetime(2024, 5, 1, tzinfo=basin.WINDOW_START_UTC.tzinfo), datetime(2024, 5, 7, tzinfo=basin.WINDOW_START_UTC.tzinfo)
    print(f"-- level signal status per hour, {lo:%m-%d} to {hi:%m-%d} UTC (144 steps)")
    for (src, stn), d in sorted(staleness_summary(steps, lo, hi).items()):
        if src == "ana_level":
            print(f"{stn:9} fresh={d['fresh']} stale={d['stale']} missing={d['missing']} max_age_h={d['max_age_h']:.1f}")

    print("-- EMS labels: first replay hour each product is visible")
    seen: dict[str, datetime] = {}
    for st in steps:
        for s in st.signals:
            if s.kind == "label" and s.station not in seen:
                seen[s.station] = st.t
                print(f"{s.station} {s.place} flooded_ha={s.value} visible from {_fmt(st.t)} ({s.reason})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
