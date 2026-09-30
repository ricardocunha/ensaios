"""Synthetic hourly rows for signal and backtest tests."""

from datetime import datetime, timedelta, timezone

from disaster_risk.dataset import HourRow
from disaster_risk.thresholds import LevelThresholds

UTC = timezone.utc
T0 = datetime(2024, 5, 1, tzinfo=UTC)


def ana_rows(levels, rains=None, station="86510000", start=T0):
    """One ANA row per hour ending start+1h, start+2h, ...; None level = silent hour."""
    rains = rains or [0.0] * len(levels)
    out, last_l, last_r = [], None, None
    for i, (lv, rn) in enumerate(zip(levels, rains)):
        h = start + timedelta(hours=i + 1)
        if lv is not None:
            last_l = h
        if rn is not None:
            last_r = h
        out.append(HourRow(
            source="ana", station=station, place="Muçum", hour_end=h, n_expected=4,
            n_received=4 if lv is not None or rn is not None else 0,
            level_n=4 if lv is not None else 0, rain_n=4 if rn is not None else 0,
            level_cm=lv, level_time=h if lv is not None else None, flow_m3s=None, rain_mm=rn,
            level_last_time=last_l, level_age_h=None if last_l is None else (h - last_l).total_seconds() / 3600,
            rain_last_time=last_r, rain_age_h=None if last_r is None else (h - last_r).total_seconds() / 3600,
            status="ok" if lv is not None else "missing",
        ))
    return out


def inmet_rows(rains, station="A840", start=T0):
    out, last = [], None
    for i, rn in enumerate(rains):
        h = start + timedelta(hours=i + 1)
        if rn is not None:
            last = h
        out.append(HourRow(
            source="inmet", station=station, place="Bento Gonçalves", hour_end=h, n_expected=1,
            n_received=int(rn is not None), level_n=0, rain_n=int(rn is not None), level_cm=None,
            level_time=None, flow_m3s=None, rain_mm=rn, level_last_time=None, level_age_h=None,
            rain_last_time=last, rain_age_h=None if last is None else (h - last).total_seconds() / 3600,
            status="ok" if rn is not None else "missing",
        ))
    return out


TH = LevelThresholds(station="86510000", n=1000, first="", last="", p50=200, p90=400, p99=1000,
                     p999=2000, max=2300, max_time="")
