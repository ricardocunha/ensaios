"""The 2019 → 2024-04 record as an hourly dataset, replayed with the same adapters.

Used for priors, the calibrated likelihood-ratio table (fitted on TRAIN only) and false alarms in quiet
periods (TEST). The replay runs in chunks of ``CHUNK`` with ``CHUNK_WARMUP`` of earlier rows; adapters
only look back 80 h, so a chunked replay equals an unchunked one (tested).
"""

from __future__ import annotations

import pickle
from bisect import bisect_left, bisect_right
from collections.abc import Iterator, Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import basin, dataset
from .backtest import Step, replay
from .dataset import HourRow
from .observations import Store
from .signals import Adapter
from .sources import inmet
from .sources._http import DATA_DIR

START = datetime(2019, 1, 1, 3, tzinfo=timezone.utc)  # 2019-01-01 00:00 local
END = datetime(2024, 4, 20, 3, tzinfo=timezone.utc)  # 2024-04-19 24:00 local, the last hour of the record
REPLAY_START = START + timedelta(days=4)  # 72 h rain windows need history
TRAIN_END = datetime(2023, 1, 1, 3, tzinfo=timezone.utc)  # TRAIN: REPLAY_START → 2022-12-31 local
TEST_START = TRAIN_END  # TEST: 2023-01-01 → 2024-04-19 local (includes the Sept and Nov 2023 floods)
# Labels need a full 24 h horizon inside the record: the last labelled hour is END - 24 h.
LABEL_END = END - timedelta(hours=24)

CHUNK = timedelta(days=30)
CHUNK_WARMUP = timedelta(days=5)


def build_rows(data_dir: Path = DATA_DIR) -> list[HourRow]:
    rows: list[HourRow] = []
    for code in basin.ANA_STATIONS:
        readings = [r for r in dataset.ana_readings(code, data_dir) if r.time < datetime(2024, 4, 20)]
        rows += dataset.ana_hourly(code, readings, START, END)
    for code in basin.INMET_STATIONS:
        hourly: list[inmet.HourlyRain] = []
        for year in range(START.year, END.year + 1):
            try:
                _, h = inmet.read_station(inmet.download_year(year, data_dir), code)
            except StopIteration:
                continue
            hourly += h
        rows += dataset.inmet_hourly(code, sorted(hourly, key=lambda r: r.time_utc), START, END)
    return rows


def cache_path(data_dir: Path = DATA_DIR) -> Path:
    return data_dir / "cache" / "hourly_history.pkl"


def load_or_build(data_dir: Path = DATA_DIR, *, rebuild: bool = False) -> list[HourRow]:
    path = cache_path(data_dir)
    if path.exists() and not rebuild:
        return pickle.loads(path.read_bytes())
    rows = build_rows(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps(rows))
    return rows


def chunked_replay(
    rows: Sequence[HourRow], adapters: Sequence[Adapter], start: datetime, end: datetime,
    chunk: timedelta = CHUNK, warmup: timedelta = CHUNK_WARMUP,
) -> Iterator[Step]:
    """Same steps as ``backtest.replay(Store(rows), adapters, start, end)``, computed chunk by chunk."""
    series: dict[tuple[str, str], list[HourRow]] = {}
    for r in rows:
        series.setdefault((r.source, r.station), []).append(r)
    for v in series.values():
        v.sort(key=lambda r: r.hour_end)
    ends = {k: [r.hour_end for r in v] for k, v in series.items()}
    lo = start
    while lo < end:
        hi = min(lo + chunk, end)
        part = []
        for k, v in series.items():
            i = bisect_left(ends[k], lo - warmup)
            j = bisect_right(ends[k], hi)
            part += v[i:j]
        yield from replay(Store(part), adapters, lo, hi)
        lo = hi
