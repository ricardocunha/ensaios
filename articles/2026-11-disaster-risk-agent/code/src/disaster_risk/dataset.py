"""Tidy hourly dataset: one row per (station, hour), UTC, no interpolation.

``uv run python -m disaster_risk.dataset`` builds ``data/cache/hourly.csv`` from
the raw ANA/INMET files (downloading what is missing) and prints coverage.

Conventions (verified, see docs/DATA.md "Time conventions"):

- Every row covers the hour ``(hour_end - 1 h, hour_end]`` in UTC, the same
  "hour ending" convention INMET uses.
- ANA ``DataHora`` is local time (UTC-3); it is shifted to UTC before binning.
  A 15-min reading stamped ``t`` is counted in the hour that contains ``t``
  (``t`` exactly on the hour belongs to the hour ending then).
- Level is the *last* level reading inside the hour, with its own timestamp.
  An hour with no level reading has ``level_cm = None``. Nothing is carried
  forward or interpolated; instead every row says when the latest reading
  was (``level_last_time``) and how old it is at ``hour_end``
  (``level_age_h``). Same for rain.
"""

from __future__ import annotations

import csv
import sys
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import basin
from .sources import ana, inmet
from .sources._http import DATA_DIR

HOUR = timedelta(hours=1)
CACHE_NAME = "hourly.csv"

ANA_EXPECTED_PER_HOUR = 4  # 15-min telemetry
INMET_EXPECTED_PER_HOUR = 1


@dataclass(frozen=True)
class HourRow:
    source: str  # "ana" | "inmet"
    station: str
    place: str
    hour_end: datetime  # UTC; the row covers (hour_end - 1 h, hour_end]
    n_expected: int  # readings the station should send per hour
    n_received: int  # rows the source returned in the hour, even if empty
    level_n: int  # readings with a level value
    rain_n: int  # readings with a rain value
    level_cm: float | None  # last level reading in the hour (gauge datum, cm)
    level_time: datetime | None  # UTC time of that reading
    flow_m3s: float | None  # flow at the same reading, if the station reports it
    rain_mm: float | None  # sum of the rain readings received in the hour
    level_last_time: datetime | None  # latest level reading at or before hour_end
    level_age_h: float | None  # hour_end - level_last_time, hours
    rain_last_time: datetime | None
    rain_age_h: float | None
    status: str  # primary variable (ANA: level, INMET: rain): "ok" | "partial" | "missing"

    @property
    def available_at(self) -> datetime:
        """Earliest moment the row can be known: the end of its hour."""
        return self.hour_end


def hour_end_of(t: datetime) -> datetime:
    """The end of the UTC hour containing ``t`` (hour-ending convention)."""
    floor = t.replace(minute=0, second=0, microsecond=0)
    return floor if floor == t else floor + HOUR


def ana_time_utc(local: datetime) -> datetime:
    return (local - basin.ANA_UTC_OFFSET).replace(tzinfo=timezone.utc)


def _hours(start: datetime, end: datetime) -> list[datetime]:
    """Hour ends in (start, end]."""
    out, h = [], start + HOUR
    while h <= end:
        out.append(h)
        h += HOUR
    return out


def _status(n: int, expected: int) -> str:
    return "ok" if n >= expected else ("partial" if n > 0 else "missing")


def _age(h: datetime, last: datetime | None) -> float | None:
    return None if last is None else (h - last).total_seconds() / 3600


def ana_hourly(station: str, readings: list[ana.Reading], start: datetime, end: datetime) -> list[HourRow]:
    """Bin 15-min ANA readings (local time) into UTC hours ``(start, end]``."""
    bins: dict[datetime, list[tuple[datetime, ana.Reading]]] = {}
    for r in readings:
        t = ana_time_utc(r.time)
        bins.setdefault(hour_end_of(t), []).append((t, r))
    last_level = last_rain = None
    # Readings before the first hour still count as "latest reading so far".
    for t, r in sorted((ana_time_utc(r.time), r) for r in readings if ana_time_utc(r.time) <= start):
        if r.level_cm is not None:
            last_level = t
        if r.rain_mm is not None:
            last_rain = t
    place = basin.STATION_PLACE.get(station, "")
    out = []
    for h in _hours(start, end):
        got = sorted(bins.get(h, []), key=lambda x: x[0])
        lv = [(t, r) for t, r in got if r.level_cm is not None]
        rn = [(t, r) for t, r in got if r.rain_mm is not None]
        if lv:
            last_level = lv[-1][0]
        if rn:
            last_rain = rn[-1][0]
        out.append(
            HourRow(
                source="ana",
                station=station,
                place=place,
                hour_end=h,
                n_expected=ANA_EXPECTED_PER_HOUR,
                n_received=len(got),
                level_n=len(lv),
                rain_n=len(rn),
                level_cm=lv[-1][1].level_cm if lv else None,
                level_time=lv[-1][0] if lv else None,
                flow_m3s=lv[-1][1].flow_m3s if lv else None,
                rain_mm=round(sum(r.rain_mm for _, r in rn), 3) if rn else None,
                level_last_time=last_level,
                level_age_h=_age(h, last_level),
                rain_last_time=last_rain,
                rain_age_h=_age(h, last_rain),
                status=_status(len(lv), ANA_EXPECTED_PER_HOUR),
            )
        )
    return out


def inmet_hourly(station: str, rows: list[inmet.HourlyRain], start: datetime, end: datetime) -> list[HourRow]:
    """INMET is already hourly, UTC, hour-ending; just align and add staleness."""
    by_hour = {r.time_utc: r for r in rows}
    last_rain = None
    for r in sorted(rows, key=lambda r: r.time_utc):
        if r.time_utc <= start and r.rain_mm is not None:
            last_rain = r.time_utc
    place = basin.STATION_PLACE.get(station, "")
    out = []
    for h in _hours(start, end):
        r = by_hour.get(h)
        has = r is not None and r.rain_mm is not None
        if has:
            last_rain = h
        out.append(
            HourRow(
                source="inmet",
                station=station,
                place=place,
                hour_end=h,
                n_expected=INMET_EXPECTED_PER_HOUR,
                n_received=int(r is not None),
                level_n=0,
                rain_n=int(has),
                level_cm=None,
                level_time=None,
                flow_m3s=None,
                rain_mm=r.rain_mm if has else None,
                level_last_time=None,
                level_age_h=None,
                rain_last_time=last_rain,
                rain_age_h=_age(h, last_rain),
                status=_status(int(has), INMET_EXPECTED_PER_HOUR),
            )
        )
    return out


def ana_readings(station: str, data_dir: Path = DATA_DIR) -> list[ana.Reading]:
    """History (up to 2024-04-19) + event window, local time, sorted."""
    hist = ana.load_telemetry(station, basin.HISTORY_START, basin.HISTORY_END, data_dir)
    event = ana.load_telemetry(station, basin.EVENT_START, basin.EVENT_END, data_dir)
    return sorted({r.time: r for r in hist + event}.values(), key=lambda r: r.time)


def build(data_dir: Path = DATA_DIR) -> list[HourRow]:
    start = basin.WINDOW_START_UTC - basin.WARMUP
    end = basin.WINDOW_END_UTC
    rows: list[HourRow] = []
    for code in basin.ANA_STATIONS:
        lo = (start - timedelta(days=7)).replace(tzinfo=None)  # enough to seed "latest reading"
        readings = [r for r in ana_readings(code, data_dir) if r.time >= lo]
        rows += ana_hourly(code, readings, start, end)
    zip_path = inmet.download_year(basin.EVENT_START.year, data_dir)
    for code in basin.INMET_STATIONS:
        _, hourly = inmet.read_station(zip_path, code)
        rows += inmet_hourly(code, hourly, start, end)
    return rows


# --- CSV cache ---------------------------------------------------------------

_TIME_FIELDS = {"hour_end", "level_time", "level_last_time", "rain_last_time"}
_INT_FIELDS = {"n_expected", "n_received", "level_n", "rain_n"}
_FLOAT_FIELDS = {"level_cm", "flow_m3s", "rain_mm", "level_age_h", "rain_age_h"}


def write_csv(rows: list[HourRow], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    names = [f.name for f in fields(HourRow)]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=names)
        w.writeheader()
        for r in rows:
            d = asdict(r)
            for k in _TIME_FIELDS:
                d[k] = d[k].strftime("%Y-%m-%dT%H:%M:%SZ") if d[k] else ""
            for k in _FLOAT_FIELDS:
                d[k] = "" if d[k] is None else repr(d[k])
            w.writerow(d)
    return path


def _parse(k: str, v: str):
    if k in _TIME_FIELDS:
        return datetime.strptime(v, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) if v else None
    if k in _INT_FIELDS:
        return int(v)
    if k in _FLOAT_FIELDS:
        return float(v) if v else None
    return v


def read_csv(path: Path) -> list[HourRow]:
    with open(path, newline="", encoding="utf-8") as fh:
        return [HourRow(**{k: _parse(k, v) for k, v in d.items()}) for d in csv.DictReader(fh)]


def cache_path(data_dir: Path = DATA_DIR) -> Path:
    return data_dir / "cache" / CACHE_NAME


def load_or_build(data_dir: Path = DATA_DIR, *, rebuild: bool = False) -> list[HourRow]:
    path = cache_path(data_dir)
    if path.exists() and not rebuild:
        return read_csv(path)
    rows = build(data_dir)
    write_csv(rows, path)
    return rows


# --- Coverage report -----------------------------------------------------------


def longest_gap_h(rows: list[HourRow]) -> tuple[float, datetime | None]:
    """Longest run of consecutive hours with status "missing", and where it starts."""
    best, best_start, run, run_start = 0, None, 0, None
    for r in rows:
        if r.status == "missing":
            if run == 0:
                run_start = r.hour_end - HOUR
            run += 1
            if run > best:
                best, best_start = run, run_start
        else:
            run = 0
    return float(best), best_start


def coverage(rows: list[HourRow], lo: datetime, hi: datetime) -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for r in rows:
        if not (lo < r.hour_end <= hi):
            continue
        c = out.setdefault((r.source, r.station), {"hours": 0, "ok": 0, "partial": 0, "missing": 0, "rows": []})
        c["hours"] += 1
        c[r.status] += 1
        c["rows"].append(r)
    for c in out.values():
        c["longest_gap_h"], c["longest_gap_start"] = longest_gap_h(c.pop("rows"))
    return out


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    rows = load_or_build(rebuild="--rebuild" in argv)
    print(f"{cache_path()} rows={len(rows)}")
    spans = [
        ("window", basin.WINDOW_START_UTC, basin.WINDOW_END_UTC),
        ("peak 05-01..05-06", datetime(2024, 5, 1, tzinfo=timezone.utc), datetime(2024, 5, 7, tzinfo=timezone.utc)),
    ]
    for label, lo, hi in spans:
        print(f"-- {label} (UTC, hours ending in ({lo:%m-%d %H:%M}, {hi:%m-%d %H:%M}])")
        for (src, st), c in coverage(rows, lo, hi).items():
            gap = c["longest_gap_start"]
            print(
                f"{src:5} {st:8} {basin.STATION_PLACE.get(st, ''):16} hours={c['hours']} ok={c['ok']} "
                f"partial={c['partial']} missing={c['missing']} longest_gap_h={c['longest_gap_h']:.0f}"
                + (f" from {gap:%m-%d %H:%M}Z" if gap else "")
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
