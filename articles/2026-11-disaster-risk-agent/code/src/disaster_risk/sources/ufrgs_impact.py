"""Municipal flood impact table for the Guaíba hydrographic region (UFRGS, Zenodo).

Record 10.5281/zenodo.11177244, CC-BY-4.0. ``analise_ada_rhguaiba_municipios.csv``
gives, per municipality, people/households and area directly affected by
water and mud as observed on 2024-05-06. We use it as ground truth for which
municipalities flooded. The full GeoPackage (~472 MB) is not downloaded.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

from ._http import DATA_DIR, fetch

RECORD = "11177244"
CSV_NAME = "analise_ada_rhguaiba_municipios.csv"
URL = f"https://zenodo.org/api/records/{RECORD}/files/{CSV_NAME}/content"


@dataclass(frozen=True)
class MunicipalImpact:
    ibge_code: str
    name: str
    people_affected: int
    people_affected_pct: float
    area_affected_pct: float


def _int(s: str) -> int:
    return int(float(s)) if s.strip() else 0


def parse_csv(text: str) -> list[MunicipalImpact]:
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        out.append(
            MunicipalImpact(
                ibge_code=r["CD_MUN"],
                name=r["NM_MUN"],
                people_affected=_int(r["Pessoas_afetadas"]),
                people_affected_pct=float(r["Pessoas_%"] or 0),
                area_affected_pct=float(r["Area_Diretamente_Afetada_Municipio_%"] or 0),
            )
        )
    return out


def download(data_dir: Path = DATA_DIR) -> Path:
    return fetch(URL, data_dir / "ufrgs" / CSV_NAME, timeout=120)


def load(data_dir: Path = DATA_DIR) -> list[MunicipalImpact]:
    return parse_csv(download(data_dir).read_text(encoding="utf-8"))
