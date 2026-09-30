"""Small, testable summaries used by the fetch script and DATA.md."""

from __future__ import annotations

from datetime import date, datetime, timezone

from .sources.ana import Reading
from .sources.inmet import HourlyRain, StationMeta


def summarize_ana(code: str, rows: list[Reading]) -> str:
    lv = [r for r in rows if r.level_cm is not None]
    if not lv:
        return f"{code} rows={len(rows)} no level data"
    peak = max(lv, key=lambda r: r.level_cm)
    return (
        f"{code} rows={len(rows)} level_rows={len(lv)} first={lv[0].time:%Y-%m-%d %H:%M} "
        f"last={lv[-1].time:%Y-%m-%d %H:%M} max_level_cm={peak.level_cm:g} at {peak.time:%Y-%m-%d %H:%M}"
    )


def rain_total(rows: list[HourlyRain], start: date, end: date) -> tuple[float, int]:
    """Sum of hourly rain in [start, end] (UTC days) and number of missing hours."""
    lo = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    hi = datetime(end.year, end.month, end.day, 23, 59, tzinfo=timezone.utc)
    win = [r for r in rows if lo <= r.time_utc <= hi]
    return sum(r.rain_mm for r in win if r.rain_mm is not None), sum(r.rain_mm is None for r in win)


def summarize_inmet(meta: StationMeta, rows: list[HourlyRain], start: date, end: date) -> str:
    total, missing = rain_total(rows, start, end)
    return f"{meta.code} {meta.name} rain_mm={total:.1f} missing_hours={missing}"
