"""Deterministic graph tools the agents call. No LLM, no network.

All functions take a simple ``nx.DiGraph`` (see ``graph.to_simple_digraph``)
whose edges carry a numeric weight (default ``travel_time`` in seconds).
Edges are identified by ``(u, v)`` node pairs.
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field

import networkx as nx
import numpy as np

Edge = tuple[int, int]
WEIGHT = "travel_time"


# --- criticality -----------------------------------------------------------


def edge_criticality(
    D: nx.DiGraph,
    k: int | None = None,
    seed: int = 42,
    weight: str = WEIGHT,
    normalized: bool = True,
) -> dict[Edge, float]:
    """Edge betweenness centrality, weighted by travel time.

    ``k=None`` is exact (one Dijkstra per node). ``k=n`` samples ``n`` source
    nodes with a fixed ``seed``, so results are reproducible.
    """
    if k is not None and k >= D.number_of_nodes():
        k = None
    return nx.edge_betweenness_centrality(
        D, k=k, normalized=normalized, weight=weight, seed=seed if k else None
    )


def top_edges(scores: dict[Edge, float], n: int = 10) -> list[tuple[Edge, float]]:
    """The ``n`` highest-scoring edges, ties broken by edge id for determinism."""
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))[:n]


# --- closure impact --------------------------------------------------------


def largest_scc(D: nx.DiGraph) -> nx.DiGraph:
    nodes = max(nx.strongly_connected_components(D), key=len)
    return D.subgraph(nodes)


def sample_od_pairs(D: nx.DiGraph, n: int, seed: int = 42) -> list[Edge]:
    """``n`` distinct origin-destination pairs from the largest strongly
    connected component (so every baseline trip exists)."""
    nodes = sorted(largest_scc(D).nodes)
    rng = random.Random(seed)
    pairs: set[Edge] = set()
    max_pairs = len(nodes) * (len(nodes) - 1)
    while len(pairs) < min(n, max_pairs):
        o, d = rng.sample(nodes, 2)
        pairs.add((o, d))
    return sorted(pairs)


def without_edges(D: nx.DiGraph, closed: Iterable[Edge]) -> nx.DiGraph:
    """A read-only view of ``D`` with ``closed`` edges removed."""
    closed = set(closed)
    return nx.subgraph_view(D, filter_edge=lambda u, v: (u, v) not in closed)


@dataclass
class TripDelta:
    origin: int
    destination: int
    before_s: float
    after_s: float | None  # None = no route after the closure

    @property
    def delta_s(self) -> float | None:
        return None if self.after_s is None else self.after_s - self.before_s


@dataclass
class ClosureImpact:
    closed_edges: list[Edge]
    n_pairs: int
    n_affected: int  # trips whose shortest path used a closed edge
    n_disconnected: int  # affected trips with no alternative route
    total_delay_s: float  # sum of extra time over affected, still-connected trips
    mean_delay_s: float  # over affected, still-connected trips (0 if none)
    max_delay_s: float
    trips: list[TripDelta] = field(default_factory=list)

    def to_dict(self, include_trips: bool = False) -> dict:
        d = asdict(self)
        if not include_trips:
            d.pop("trips")
        return d


@dataclass
class Baseline:
    """Shortest trips for a fixed set of OD pairs, computed once and reused
    across many closure scenarios."""

    od_pairs: list[Edge]
    time_s: dict[Edge, float]  # only pairs with a route
    edges: dict[Edge, frozenset[Edge]]  # edges on each pair's shortest path


def compute_baseline(D: nx.DiGraph, od_pairs: Sequence[Edge], weight: str = WEIGHT) -> Baseline:
    """Bidirectional Dijkstra per pair (much faster than a full search from
    each origin on a city graph)."""
    time_s: dict[Edge, float] = {}
    edges: dict[Edge, frozenset[Edge]] = {}
    for o, d in od_pairs:
        try:
            t, p = nx.bidirectional_dijkstra(D, o, d, weight=weight)
        except nx.NetworkXNoPath:
            continue
        time_s[(o, d)] = float(t)
        edges[(o, d)] = frozenset(zip(p, p[1:]))
    return Baseline(list(od_pairs), time_s, edges)


def closure_impact(
    D: nx.DiGraph,
    closed: Iterable[Edge],
    od_pairs: Sequence[Edge] | Baseline,
    weight: str = WEIGHT,
) -> ClosureImpact:
    """Shortest-path travel-time deltas for ``od_pairs`` when ``closed`` edges
    are removed. Pass a ``Baseline`` (see ``compute_baseline``) to reuse the
    no-closure trips across scenarios.

    Exact, not an estimate: a trip whose baseline shortest path avoids every
    closed edge keeps the same travel time (removing edges never makes a path
    shorter, and its old path is still there), so only trips through a closed
    edge are recomputed.
    """
    closed = sorted(set(closed))
    missing = [e for e in closed if not D.has_edge(*e)]
    if missing:
        raise KeyError(f"edges not in graph: {missing}")
    base = od_pairs if isinstance(od_pairs, Baseline) else compute_baseline(D, od_pairs, weight)
    closed_set = set(closed)

    def w(u, v, data):  # a None weight hides the edge (faster than a subgraph view)
        return None if (u, v) in closed_set else data[weight]

    trips: list[TripDelta] = []
    for pair, before in base.time_s.items():
        if closed_set.isdisjoint(base.edges[pair]):
            continue
        o, d = pair
        try:
            after = float(nx.bidirectional_dijkstra(D, o, d, weight=w)[0])
        except nx.NetworkXNoPath:
            after = None
        trips.append(TripDelta(o, d, before, after))
    connected = [t.delta_s for t in trips if t.delta_s is not None]
    return ClosureImpact(
        closed_edges=closed,
        n_pairs=len(base.od_pairs),
        n_affected=len(trips),
        n_disconnected=sum(t.after_s is None for t in trips),
        total_delay_s=float(sum(connected)),
        mean_delay_s=float(np.mean(connected)) if connected else 0.0,
        max_delay_s=float(max(connected)) if connected else 0.0,
        trips=trips,
    )


# --- accessibility ---------------------------------------------------------


def snap_points(D: nx.DiGraph, points: Sequence[tuple[float, float]]) -> list[int]:
    """Nearest graph node for each ``(lon, lat)`` point (haversine, brute force;
    fine for tens of thousands of nodes and hundreds of points)."""
    ids = np.array(list(D.nodes))
    lon = np.radians([D.nodes[n]["x"] for n in ids])
    lat = np.radians([D.nodes[n]["y"] for n in ids])
    out = []
    for px, py in points:
        px, py = np.radians(px), np.radians(py)
        h = np.sin((lat - py) / 2) ** 2 + np.cos(py) * np.cos(lat) * np.sin((lon - px) / 2) ** 2
        out.append(int(ids[int(np.argmin(h))]))
    return out


def time_to_nearest(
    D: nx.DiGraph,
    facilities: Iterable[int],
    weight: str = WEIGHT,
    cutoff: float | None = None,
) -> dict[int, float]:
    """Travel time from every node to its nearest facility (multi-source
    Dijkstra on the reversed graph). Nodes that can't reach any facility
    (or only beyond ``cutoff``) are absent."""
    sources = set(facilities)
    if not sources:
        return {}
    return nx.multi_source_dijkstra_path_length(
        D.reverse(copy=False), sources, cutoff=cutoff, weight=weight
    )


def isochrone(
    D: nx.DiGraph, source: int, cutoff_s: float, weight: str = WEIGHT
) -> set[int]:
    """Nodes reachable from ``source`` within ``cutoff_s`` seconds."""
    return set(nx.single_source_dijkstra_path_length(D, source, cutoff=cutoff_s, weight=weight))


def accessibility(
    D: nx.DiGraph,
    facilities: Iterable[int],
    thresholds_s: Sequence[float] = (300, 600, 900),
    weight: str = WEIGHT,
) -> dict:
    """Share of nodes that reach a facility within each threshold, plus the
    median and 95th-percentile time among nodes that reach one at all."""
    t = time_to_nearest(D, facilities, weight=weight)
    n = D.number_of_nodes()
    times = np.array(sorted(t.values())) if t else np.array([])
    return {
        "n_nodes": n,
        "n_reachable": len(t),
        "share_within": {int(s): (float((times <= s).sum()) / n if n else 0.0) for s in thresholds_s},
        "median_s": float(np.median(times)) if len(times) else None,
        "p95_s": float(np.percentile(times, 95)) if len(times) else None,
    }


def accessibility_loss(
    D: nx.DiGraph,
    facilities: Iterable[int],
    closed: Iterable[Edge],
    threshold_s: float = 600,
    weight: str = WEIGHT,
) -> dict:
    """Nodes that reach a facility within ``threshold_s`` before the closure
    but not after."""
    facilities = list(facilities)
    before = time_to_nearest(D, facilities, weight=weight, cutoff=threshold_s)
    after = time_to_nearest(without_edges(D, closed), facilities, weight=weight, cutoff=threshold_s)
    lost = sorted(set(before) - set(after))
    return {"threshold_s": threshold_s, "n_before": len(before), "n_after": len(after), "lost_nodes": lost}
