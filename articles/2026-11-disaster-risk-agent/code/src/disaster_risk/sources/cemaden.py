"""CEMADEN automatic rain gauges.

Historical data: monthly CSV per state from the "Download de Dados" form at
https://mapainterativo.cemaden.gov.br/download/download_form.php. The form
posts to ``download_file.php`` and requires a CAPTCHA (securimage), so it
cannot be scripted here. To use it, download RS April and May 2024 by hand
and save them as ``data/cemaden/RS_2024_04.csv`` and ``RS_2024_05.csv``.

The REST API at sws.cemaden.gov.br/PED/rest needs a token
("O parâmetro token não pode ser vazio!") that requires registration.

What works without a key is the live snapshot behind the interactive map
(``getJson2.php``): current accumulations only, no history.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ._http import DATA_DIR, fetch

SNAPSHOT_URL = "https://resources.cemaden.gov.br/graficos/interativo/getJson2.php?uf={uf}"


@dataclass(frozen=True)
class GaugeSnapshot:
    station_id: int
    ibge_code: int
    city: str
    name: str
    last_time: str
    acc24h_mm: float | None


def manual_path(uf: str, year: int, month: int, data_dir: Path = DATA_DIR) -> Path:
    return data_dir / "cemaden" / f"{uf}_{year}_{month:02d}.csv"


def require_manual(uf: str, year: int, month: int, data_dir: Path = DATA_DIR) -> Path:
    p = manual_path(uf, year, month, data_dir)
    if not p.exists():
        raise FileNotFoundError(
            f"{p} not found. CEMADEN historical downloads are behind a CAPTCHA: "
            "download it by hand from https://mapainterativo.cemaden.gov.br "
            "(Download de Dados > Pluviômetros) and save it at that path."
        )
    return p


def _num(v) -> float | None:
    return None if v in (None, "-", "") else float(v)


def parse_snapshot(raw: bytes) -> list[GaugeSnapshot]:
    rows = json.loads(raw.decode("utf-8-sig"))
    return [
        GaugeSnapshot(
            station_id=r["idestacao"],
            ibge_code=r["codibge"],
            city=r["cidade"],
            name=r["nomeestacao"],
            last_time=r["datahoraUltimovalor"],
            acc24h_mm=_num(r.get("acc24hr")),
        )
        for r in rows
    ]


def download_snapshot(uf: str, dest_name: str, data_dir: Path = DATA_DIR) -> Path:
    """Live snapshot; ``dest_name`` should carry the retrieval date, it changes every hour."""
    return fetch(SNAPSHOT_URL.format(uf=uf), data_dir / "cemaden" / dest_name, timeout=60)
