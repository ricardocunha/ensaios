"""Download the audit dataset into code/data/ (cached). ``uv run python -m disaster_risk.fetch``."""

from __future__ import annotations

import sys

from . import basin
from ._summary import summarize_ana, summarize_inmet
from .sources import ana, cemaden, copernicus_ems, inmet, s2id, sgb_sace, ufrgs_impact
from .sources._http import BlockedError


def main() -> int:
    status: dict[str, str] = {}

    for code in basin.ANA_STATIONS:
        rows = ana.load_telemetry(code, basin.EVENT_START, basin.EVENT_END)
        print("ANA", summarize_ana(code, rows))
    status["ana"] = "works"

    # Historical record for station thresholds (milestone 2), ~2019 → day before the window.
    for code in basin.ANA_STATIONS:
        rows = ana.load_telemetry(code, basin.HISTORY_START, basin.HISTORY_END)
        print("ANA history", summarize_ana(code, rows))

    # SGB SACE Taquari alert bulletins (official alert times), April-May 2024.
    bulletins = [b for b in sgb_sace.list_bulletins() if b.nominal.year == 2024 and b.nominal.month in (4, 5)]
    for b in bulletins:
        sgb_sace.pdf_text(sgb_sace.download_bulletin(b))
    print(f"SGB SACE Taquari bulletins 2024-04/05: {len(bulletins)}")
    status["sgb_sace"] = "works"

    zip_path = inmet.download_year(basin.EVENT_START.year)
    for code in basin.INMET_STATIONS:
        meta, rows = inmet.read_station(zip_path, code)
        print("INMET", summarize_inmet(meta, rows, basin.EVENT_START, basin.EVENT_END))
    status["inmet"] = "works"

    products = copernicus_ems.list_products(basin.EMS_ACTIVATION)
    for p in products:
        if p.kind == "DEL":
            path = copernicus_ems.download_product(p)
            n = len(copernicus_ems.read_observed_event(path)["features"])
            print(f"EMS {p.filename} {p.aoi_name} {p.sensor} {p.acquired} flood_polygons={n}")
    status["copernicus_ems"] = "works"

    impacts = ufrgs_impact.load()
    print(f"UFRGS municipal impact rows={len(impacts)}")
    status["ufrgs_impact"] = "works"

    for month in (4, 5):
        try:
            cemaden.require_manual("RS", 2024, month)
            status[f"cemaden_{month}"] = "manual file present"
        except FileNotFoundError as e:
            status[f"cemaden_{month}"] = "blocked (captcha)"
            print("CEMADEN", e)

    try:
        s2id.download_history()
        status["s2id"] = "works"
    except BlockedError as e:
        status["s2id"] = "blocked (WAF)"
        print("S2iD", e)

    print(status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
