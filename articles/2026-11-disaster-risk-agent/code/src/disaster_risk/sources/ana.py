"""ANA telemetry (Rede Hidrometeorológica Nacional), legacy SOAP/HTTP-GET service.

No key needed. 15-minute readings of level (``Nivel``, cm), discharge
(``Vazao``, m³/s) and rain (``Chuva``, mm per interval).

The newer REST ``HidroWebService`` (www.ana.gov.br/hidrowebservice) returns
HTTP 401 without credentials, so we use the legacy endpoint.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from ._http import DATA_DIR, fetch

BASE = "http://telemetriaws1.ana.gov.br/ServiceANA.asmx"


@dataclass(frozen=True)
class Reading:
    station: str
    time: datetime  # as served by ANA: naive local time, UTC-3 (see basin.ANA_UTC_OFFSET)
    level_cm: float | None
    flow_m3s: float | None
    rain_mm: float | None


@dataclass(frozen=True)
class Station:
    code: str
    name: str
    municipality: str
    river: str
    origin: str
    lat: float
    lon: float


def _num(text: str | None) -> float | None:
    if text is None or not text.strip():
        return None
    return float(text)


def telemetry_url(station: str, start: date, end: date) -> str:
    return (
        f"{BASE}/DadosHidrometeorologicos?codEstacao={station}"
        f"&dataInicio={start:%d/%m/%Y}&dataFim={end:%d/%m/%Y}"
    )


def parse_telemetry(xml_bytes: bytes) -> list[Reading]:
    """Parse the DataSet XML into readings sorted by time.

    Rows where the station sent nothing at all (level, flow and rain all
    empty) are kept: a gap is information too (see Estrela on 2024-05-06).
    """
    root = ET.fromstring(xml_bytes)
    out = []
    for row in root.iter("DadosHidrometereologicos"):  # sic, ANA's spelling
        f = {c.tag: c.text for c in row}
        out.append(
            Reading(
                station=(f.get("CodEstacao") or "").strip(),
                time=datetime.strptime(f["DataHora"].strip(), "%Y-%m-%d %H:%M:%S"),
                level_cm=_num(f.get("Nivel")),
                flow_m3s=_num(f.get("Vazao")),
                rain_mm=_num(f.get("Chuva")),
            )
        )
    out.sort(key=lambda r: r.time)
    return out


def parse_inventory(xml_bytes: bytes) -> list[Station]:
    root = ET.fromstring(xml_bytes)
    out = []
    for row in root.iter("Table"):
        f = {c.tag: (c.text or "").strip() for c in row}
        out.append(
            Station(
                code=f.get("CodEstacao", ""),
                name=f.get("NomeEstacao", ""),
                municipality=f.get("Municipio-UF", ""),
                river=f.get("NomeRio", ""),
                origin=f.get("Origem", ""),
                lat=float(f.get("Latitude") or "nan"),
                lon=float(f.get("Longitude") or "nan"),
            )
        )
    return out


def download_telemetry(station: str, start: date, end: date, data_dir: Path = DATA_DIR) -> Path:
    dest = data_dir / "ana" / f"telemetry_{station}_{start:%Y%m%d}_{end:%Y%m%d}.xml"
    return fetch(telemetry_url(station, start, end), dest, timeout=180)


def download_inventory(data_dir: Path = DATA_DIR) -> Path:
    url = f"{BASE}/ListaEstacoesTelemetricas?statusEstacoes=0&origem="
    return fetch(url, data_dir / "ana" / "inventory.xml", timeout=180)


def load_telemetry(station: str, start: date, end: date, data_dir: Path = DATA_DIR) -> list[Reading]:
    return parse_telemetry(download_telemetry(station, start, end, data_dir).read_bytes())
