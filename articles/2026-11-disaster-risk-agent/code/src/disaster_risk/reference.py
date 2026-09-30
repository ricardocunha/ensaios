"""Reference times for "would it have warned in time", per gauge / municipality.

No machine-readable record of *municipal* alert times (Defesa Civil RS,
CEMADEN) was found for the 2024 event (docs/DATA.md). What we have:

1. **Official hydrological bulletins** (SGB SACE Taquari): the time of the
   first extraordinary bulletin for the basin, and the first bulletin that
   printed a station at or above its flood level. Times from file names
   (nominal data time and upload time), local UTC-3.
2. **Flood-level crossing** from ANA telemetry: the first 15-min reading at or
   above the official flood level (``basin.FLOOD_LEVEL_CM``). This is the
   fallback "in time" reference: an alert is in time if it precedes this.
3. **Gauge peak**: the highest reading in the window, with a flag when the
   gauge stopped reporting before the river did.

``uv run python -m disaster_risk.reference`` prints the table used in RESULTS.md.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta

from . import basin, dataset
from .sources import ana, sgb_sace

# SACE station names as printed in the bulletins -> ANA codes.
SACE_TO_ANA = {"Muçum": "86510000", "Encantado": "86720000", "Estrela": "86879300", "Taquari": "86950000"}


@dataclass(frozen=True)
class Crossing:
    station: str
    flood_cm: float | None
    first_at_or_above: datetime | None  # local time of the first reading >= flood level
    peak_cm: float | None
    peak_time: datetime | None
    last_level_time: datetime | None  # last level reading in the window
    gauge_silent_h_after_crossing: float | None  # longest level gap in the 72 h after the first crossing


def first_crossing(readings: list[ana.Reading], flood_cm: float) -> datetime | None:
    for r in readings:
        if r.level_cm is not None and r.level_cm >= flood_cm:
            return r.time
    return None


def longest_gap_h(readings: list[ana.Reading], lo: datetime, hi: datetime) -> float:
    """Longest stretch without a level reading inside [lo, hi], counting both ends."""
    times = [lo] + [r.time for r in readings if r.level_cm is not None and lo <= r.time <= hi] + [hi]
    return max((b - a).total_seconds() / 3600 for a, b in zip(times, times[1:]))


def crossing(station: str, readings: list[ana.Reading], flood_cm: float | None) -> Crossing:
    lv = [r for r in readings if r.level_cm is not None]
    peak = max(lv, key=lambda r: r.level_cm) if lv else None
    first = first_crossing(readings, flood_cm) if flood_cm is not None else None
    gap = None
    if first is not None:
        gap = longest_gap_h(readings, first, first + timedelta(hours=72))
    return Crossing(
        station=station,
        flood_cm=flood_cm,
        first_at_or_above=first,
        peak_cm=peak.level_cm if peak else None,
        peak_time=peak.time if peak else None,
        last_level_time=lv[-1].time if lv else None,
        gauge_silent_h_after_crossing=gap,
    )


@dataclass(frozen=True)
class BulletinRef:
    first_bulletin: sgb_sace.Bulletin | None
    first_at_flood: dict[str, sgb_sace.Bulletin]  # ANA code -> first bulletin with level >= flood level


def bulletin_reference(bulletins: list[tuple[sgb_sace.Bulletin, list[sgb_sace.StationRow]]]) -> BulletinRef:
    first = bulletins[0][0] if bulletins else None
    at_flood: dict[str, sgb_sace.Bulletin] = {}
    for b, rows in bulletins:
        for r in rows:
            code = SACE_TO_ANA.get(r.station)
            if code is None or code in at_flood:
                continue
            if r.level_cm is not None and r.flood_level_cm is not None and r.level_cm >= r.flood_level_cm:
                at_flood[code] = b
    return BulletinRef(first, at_flood)


def load_bulletins(year: int = 2024, months: tuple[int, ...] = (4, 5)):
    out = []
    for b in sgb_sace.list_bulletins():
        if b.nominal.year == year and b.nominal.month in months:
            text = sgb_sace.pdf_text(sgb_sace.download_bulletin(b))
            out.append((b, sgb_sace.parse_bulletin_text(text)[1] if text else []))
    return out


def _t(t: datetime | None) -> str:
    return "—" if t is None else f"{t:%m-%d %H:%M}"


def main() -> int:
    bl = load_bulletins()
    ref = bulletin_reference(bl)
    fb = ref.first_bulletin
    in_window = [b for b, _ in bl if b.nominal < datetime(2024, 5, 7)]
    print(f"SACE Taquari bulletins Apr-May 2024: {len(bl)} (30/04-06/05: {len(in_window)})")
    if fb:
        print(f"first bulletin: data {_t(fb.nominal)} local, uploaded {_t(fb.uploaded)} local")
    print("station | flood cm | first reading >= flood (local) | first bulletin >= flood (data / upload) | peak cm at (local) | last level reading | longest level gap in 72 h after crossing")
    for code, (name, _) in basin.ANA_STATIONS.items():
        readings = [r for r in dataset.ana_readings(code) if r.time >= datetime(2024, 4, 20)]
        c = crossing(code, readings, basin.FLOOD_LEVEL_CM.get(code))
        b = ref.first_at_flood.get(code)
        print(
            f"{code} {name} | {c.flood_cm or '—'} | {_t(c.first_at_or_above)} | "
            f"{(_t(b.nominal) + ' / ' + _t(b.uploaded)) if b else '—'} | {c.peak_cm} at {_t(c.peak_time)} | "
            f"{_t(c.last_level_time)} | {'—' if c.gauge_silent_h_after_crossing is None else f'{c.gauge_silent_h_after_crossing:.1f} h'}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
