"""Compute sampled edge betweenness once and cache it as CSV in data/.

Usage:
    nice uv run python scripts/cache_betweenness.py belo-horizonte --k 2000
"""

from __future__ import annotations

import argparse
import time

from road_agents.graph import load_graph, to_simple_digraph
from road_agents.sections import betweenness_cache_path, save_scores


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("city")
    p.add_argument("--k", type=int, default=500)
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args()
    from road_agents.tools import edge_criticality

    D = to_simple_digraph(load_graph(a.city))
    t = time.perf_counter()
    scores = edge_criticality(D, k=a.k, seed=a.seed)
    dt = time.perf_counter() - t
    path = betweenness_cache_path(a.city, a.k, a.seed)
    save_scores(scores, path)
    print(f"{a.city} k={a.k} seed={a.seed}: {dt:.1f} s -> {path}")


if __name__ == "__main__":
    main()
