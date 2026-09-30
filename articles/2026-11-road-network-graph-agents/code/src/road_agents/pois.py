"""Hospitals and schools from OSM (ODbL), cached as CSV in data/."""

from __future__ import annotations

import csv
from pathlib import Path

from road_agents.graph import CITIES, DATA_DIR, slugify

POI_TAGS = {
    "hospital": {"amenity": "hospital"},
    "school": {"amenity": "school"},
}


def load_pois(place: str, kind: str, data_dir: Path | None = None, refresh: bool = False) -> list[dict]:
    """Return ``[{"osm_id", "name", "lon", "lat"}, ...]`` for ``kind`` in POI_TAGS.

    Polygons (most hospitals and schools are mapped as areas) are reduced to
    their centroid. Downloads with OSMnx once, then reads the CSV cache.
    """
    path = (data_dir or DATA_DIR) / f"{slugify(place)}-{kind}.csv"
    if path.exists() and not refresh:
        with open(path, newline="") as f:
            return [
                {**r, "lon": float(r["lon"]), "lat": float(r["lat"])} for r in csv.DictReader(f)
            ]
    import osmnx as ox

    ox.settings.cache_folder = str(path.parent / "osmnx-http-cache")
    gdf = ox.features_from_place(CITIES.get(place, place), tags=POI_TAGS[kind])
    rows = []
    for (etype, oid), row in gdf.iterrows():
        c = row.geometry.centroid  # degrees; fine for snapping to the nearest node
        name = row.get("name")
        rows.append(
            {
                "osm_id": f"{etype}/{oid}",
                "name": name if isinstance(name, str) else "",
                "lon": round(c.x, 7),
                "lat": round(c.y, 7),
            }
        )
    rows.sort(key=lambda r: r["osm_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["osm_id", "name", "lon", "lat"])
        w.writeheader()
        w.writerows(rows)
    return rows
