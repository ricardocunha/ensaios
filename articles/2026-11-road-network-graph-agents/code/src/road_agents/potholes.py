"""Belo Horizonte "Tapa-Buraco" (pothole repair) requests from BH Digital.

Source: PBH open data, "Solicitações dos cidadãos, por meio dos canais de
atendimento da PBH" (CC-BY; see docs/DATA.md). Monthly/yearly CSVs are
cached in ``data/pbh/`` (git-ignored).

Privacy rule for this project: request coordinates are only used in memory
to snap requests to road sections; nothing per request is written out or
published, only per-section counts.
"""

from __future__ import annotations

import io
import urllib.request
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from road_agents.graph import DATA_DIR

PBH_DIR = DATA_DIR / "pbh"
BASE = "https://ckan.pbh.gov.br/dataset/94ad6240-2131-44d4-9f96-3f350dcf2bee/resource"

# Files on dados.pbh.gov.br as of 2026-09-30 (2020 May-Dec, 2021 and 2022 are
# yearly files; 2023 is monthly up to July).
FILES = {
    "2020": "905e4677-a30c-453d-bd44-7f34d8d149e4/download/dadosabertos_bhdigital_2020_mai-dez.csv",
    "2021": "fa3bfdfb-570e-492c-9b3e-9a2fc8421e74/download/dadosabertos_bhdigital_2021.csv",
    "2022": "54a1d639-e44c-4927-ad2d-542fd26c2c2d/download/dadosabertos_bhdigital_2022.csv",
    "2023-01": "feba8392-ff66-4b05-868e-06e97c03dd32/download/dadosabertos_bhdigital_2023_jan.csv",
    "2023-02": "52226a89-1f89-4800-98a4-6e5d0dff8313/download/dadosabertos_bhdigital_2023_fev.csv",
    "2023-03": "be1ce043-4d53-4009-8368-e87deb95f92c/download/dadosabertos_bhdigital_2023_mar.csv",
    "2023-04": "b0b4de0e-2ba9-401a-966c-7c9602093c9b/download/dadosabertos_bhdigital_2023_abr.csv",
    "2023-05": "464fa0bd-b241-4abe-9935-58813b9e4a3d/download/dadosabertos_bhdigital_2023_mai.csv",
    "2023-06": "b0275843-33e7-428b-8cb1-5aea0a3a45b7/download/dadosabertos_bhdigital_2023_jun.csv",
    "2023-07": "f2f02df6-b1db-46bc-9029-f98a2c878672/download/dadosabertos_bhdigital_2023_jul.csv",
}

COLUMNS = [
    "ticket",
    "service",
    "created",
    "closed",
    "phase",
    "status",
    "channel",
    "agency_norm",
    "agency_resp",
    "street",
    "number",
    "neighbourhood",
    "regional",
    "coords",
    "in_app",
    "access_level",
]
POTHOLE_SERVICE = "Tapa-Buraco"
# Projected CRS used by PBH (SIRGAS 2000 / UTM 23S), in metres.
METRIC_CRS = "EPSG:31983"


def download(key: str, data_dir: Path | None = None, refresh: bool = False) -> Path:
    """Download one file of FILES (cached). The CKAN API blocks scripted
    clients, but direct resource downloads work with a browser user agent."""
    path = (data_dir or PBH_DIR) / Path(FILES[key]).name
    if path.exists() and not refresh:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(f"{BASE}/{FILES[key]}", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=300) as r, open(path, "wb") as f:
        f.write(r.read())
    return path


def read_requests(source: Path | bytes, service: str | None = POTHOLE_SERVICE) -> pd.DataFrame:
    """Read one BH Digital CSV (either format) into a tidy frame.

    The 2022 file is Latin-1 with ISO dates; the 2023 files are UTF-8 with a
    BOM and ``dd/mm/yyyy`` dates (although the header says YYYY-MM-DD). Both
    are ``;``-separated with the same 16 columns. Returns ``ticket, service,
    created, channel, status, access_level, lat, lon`` (lat/lon NaN when
    missing), filtered to ``service`` unless it is None.
    """
    raw = source if isinstance(source, bytes) else Path(source).read_bytes()
    enc = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "latin-1"
    df = pd.read_csv(io.BytesIO(raw), sep=";", encoding=enc, dtype=str, keep_default_na=False)
    if len(df.columns) != len(COLUMNS):
        raise ValueError(f"expected {len(COLUMNS)} columns, got {len(df.columns)}")
    df.columns = COLUMNS
    if service is not None:
        df = df[df["service"].str.strip() == service]
    created = df["created"].str.strip()
    iso = created.str.match(r"^\d{4}-\d{2}-\d{2}")
    dates = pd.Series(pd.NaT, index=df.index, dtype="datetime64[ns]")
    dates[iso] = pd.to_datetime(created[iso].str[:10], format="%Y-%m-%d", errors="coerce")
    dates[~iso] = pd.to_datetime(created[~iso].str[:10], format="%d/%m/%Y", errors="coerce")
    latlon = df["coords"].str.split(",", n=1, expand=True).reindex(columns=[0, 1])
    lat = pd.to_numeric(latlon[0].str.strip(), errors="coerce")
    lon = pd.to_numeric(latlon[1].str.strip(), errors="coerce")
    return pd.DataFrame(
        {
            "ticket": df["ticket"].str.strip(),
            "service": df["service"].str.strip(),
            "created": dates,
            "channel": df["channel"].str.strip(),
            "status": df["status"].str.strip(),
            "access_level": df["access_level"].str.strip(),
            "lat": lat,
            "lon": lon,
        }
    ).reset_index(drop=True)


def load_requests(
    keys: list[str], start: str, end: str, data_dir: Path | None = None
) -> pd.DataFrame:
    """Pothole requests created in ``[start, end]`` (inclusive dates) from the
    given FILES keys, de-duplicated by ticket id."""
    frames = [read_requests(download(k, data_dir)) for k in keys]
    df = pd.concat(frames, ignore_index=True).drop_duplicates("ticket")
    mask = (df["created"] >= pd.Timestamp(start)) & (df["created"] <= pd.Timestamp(end))
    return df[mask].reset_index(drop=True)


# --- snapping --------------------------------------------------------------


def links_frame(D, links: dict[tuple[int, int], str]) -> gpd.GeoDataFrame:
    """One row per undirected link with its section id and geometry (the
    OSM edge geometry when present, else a straight line), in METRIC_CRS."""
    geoms, lids, sids = [], [], []
    for (u, v), sid in links.items():
        data = D[u][v] if D.has_edge(u, v) else D[v][u]
        g = data.get("geometry")
        if g is None:
            a, b = (u, v) if D.has_edge(u, v) else (v, u)
            g = shapely.LineString([(D.nodes[a]["x"], D.nodes[a]["y"]), (D.nodes[b]["x"], D.nodes[b]["y"])])
        geoms.append(g)
        lids.append(f"{u}-{v}")
        sids.append(sid)
    return gpd.GeoDataFrame({"link": lids, "section_id": sids}, geometry=geoms, crs="EPSG:4326").to_crs(METRIC_CRS)


def snap_requests(
    requests: pd.DataFrame, links: gpd.GeoDataFrame, max_distance_m: float = 30.0
) -> pd.DataFrame:
    """Nearest link for each request with coordinates.

    Returns one row per input request (same order) with ``section_id`` (None
    when no link is within ``max_distance_m`` or coordinates are missing) and
    ``distance_m`` (to the nearest link, searched up to 10x the threshold;
    NaN beyond that). Coordinates are SIRGAS 2000, treated as WGS 84 (they
    differ by centimetres). Ties between equidistant links go to the lowest
    link id, so results are deterministic.
    """
    has = requests["lat"].notna() & requests["lon"].notna()
    out = pd.DataFrame(
        {"section_id": pd.Series([None] * len(requests), dtype=object), "distance_m": np.nan},
        index=requests.index,
    )
    if not has.any():
        return out
    pts = gpd.GeoDataFrame(
        {"_row": np.flatnonzero(has.to_numpy())},
        geometry=gpd.points_from_xy(requests.loc[has, "lon"], requests.loc[has, "lat"]),
        crs="EPSG:4326",
    ).to_crs(METRIC_CRS)
    j = gpd.sjoin_nearest(pts, links, how="left", max_distance=10 * max_distance_m, distance_col="distance_m")
    j = j.sort_values(["_row", "link"]).drop_duplicates("_row")
    rows = requests.index[j["_row"].to_numpy()]
    out.loc[rows, "distance_m"] = j["distance_m"].to_numpy()
    ok = j["distance_m"].to_numpy() <= max_distance_m
    out.loc[rows[ok], "section_id"] = j["section_id"].to_numpy()[ok]
    return out
