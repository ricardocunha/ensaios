"""INMET automatic weather stations, yearly bulk CSV archive.

``https://portal.inmet.gov.br/uploads/dadoshistoricos/<year>.zip`` has one
CSV per station, hourly, times in UTC. No key needed, but the server resets
connections that do not send a browser-like User-Agent.

The JSON API (apitempo.inmet.gov.br/estacao/...) answered HTTP 204 without
a token on 2026-09-30, so we use the bulk file.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ._http import DATA_DIR, fetch

MISSING = {"", "-9999"}


@dataclass(frozen=True)
class HourlyRain:
    station: str
    time_utc: datetime  # end of the hour the total refers to [[VERIFY]]
    rain_mm: float | None


@dataclass(frozen=True)
class StationMeta:
    code: str
    name: str
    lat: float
    lon: float


def year_url(year: int) -> str:
    return f"https://portal.inmet.gov.br/uploads/dadoshistoricos/{year}.zip"


def download_year(year: int, data_dir: Path = DATA_DIR) -> Path:
    return fetch(year_url(year), data_dir / "inmet" / f"{year}.zip", timeout=900)


def _br_float(s: str) -> float | None:
    s = s.strip()
    return None if s in MISSING else float(s.replace(",", "."))


def parse_station_csv(text: str) -> tuple[StationMeta, list[HourlyRain]]:
    """Parse one station CSV (8 metadata lines, header, then ';'-separated rows)."""
    lines = text.splitlines()
    meta = {}
    for line in lines[:8]:
        k, _, v = line.partition(";")
        meta[k.strip().rstrip(":")] = v.strip()
    header = lines[8].split(";")
    rain_col = next(i for i, h in enumerate(header) if h.startswith("PRECIPITA"))
    code = meta["CODIGO (WMO)"]
    rows = []
    for line in lines[9:]:
        cols = line.split(";")
        if len(cols) <= rain_col:
            continue
        t = datetime.strptime(f"{cols[0]} {cols[1][:4]}", "%Y/%m/%d %H%M").replace(tzinfo=timezone.utc)
        rows.append(HourlyRain(code, t, _br_float(cols[rain_col])))
    station = StationMeta(
        code=code,
        name=meta.get("ESTACAO", ""),
        lat=_br_float(meta.get("LATITUDE", "")) or float("nan"),
        lon=_br_float(meta.get("LONGITUDE", "")) or float("nan"),
    )
    return station, rows


def read_station(zip_path: Path, code: str) -> tuple[StationMeta, list[HourlyRain]]:
    with zipfile.ZipFile(zip_path) as z:
        name = next(n for n in z.namelist() if f"_{code}_" in n)
        return parse_station_csv(z.read(name).decode("latin-1"))


def load_station(year: int, code: str, data_dir: Path = DATA_DIR) -> tuple[StationMeta, list[HourlyRain]]:
    return read_station(download_year(year, data_dir), code)
