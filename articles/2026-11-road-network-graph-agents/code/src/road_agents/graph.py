"""Load and cache a city's drivable road graph from OpenStreetMap.

OSM data is (c) OpenStreetMap contributors, licensed under the ODbL.
The GraphML cache lives in ``data/`` (git-ignored).
"""

from __future__ import annotations

import re
from pathlib import Path

import networkx as nx

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

CITIES = {
    "porto-alegre": "Porto Alegre, Rio Grande do Sul, Brazil",
    "belo-horizonte": "Belo Horizonte, Minas Gerais, Brazil",
}


def slugify(place: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", place.lower()).strip("-")


def cache_path(place: str, data_dir: Path | None = None) -> Path:
    return (data_dir or DATA_DIR) / f"{slugify(place)}-drive.graphml"


def load_graph(
    place: str, data_dir: Path | None = None, refresh: bool = False
) -> nx.MultiDiGraph:
    """Return the drivable graph for ``place`` (a key of CITIES or a geocodable name).

    Downloads with OSMnx on the first call and caches as GraphML; later calls
    read the cache. Edges get ``speed_kph`` and ``travel_time`` (seconds).
    """
    import osmnx as ox

    query = CITIES.get(place, place)
    path = cache_path(place, data_dir)
    if path.exists() and not refresh:
        return ox.load_graphml(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ox.settings.cache_folder = str(path.parent / "osmnx-http-cache")
    G = ox.graph_from_place(query, network_type="drive", simplify=True)
    G = ox.add_edge_speeds(G)
    G = ox.add_edge_travel_times(G)
    ox.save_graphml(G, path)
    return G


def to_simple_digraph(G: nx.MultiDiGraph, weight: str = "travel_time") -> nx.DiGraph:
    """Collapse parallel edges, keeping the one with the smallest ``weight``.

    The returned edges keep that edge's attributes plus ``key`` (the original
    multigraph key), so results map back to OSM edges.
    """
    D = nx.DiGraph()
    D.add_nodes_from(G.nodes(data=True))
    for u, v, k, data in G.edges(keys=True, data=True):
        w = float(data.get(weight, data.get("length", 1.0)))
        if D.has_edge(u, v) and float(D[u][v][weight]) <= w:
            continue
        attrs = dict(data)
        attrs[weight] = w
        attrs["key"] = k
        D.add_edge(u, v, **attrs)
    return D
