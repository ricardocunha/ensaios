"""Time edge betweenness (exact vs. sampled k) on a cached city graph.

Usage:
    uv run python scripts/bench_betweenness.py porto-alegre --k 100 500 2000 --exact

Writes a JSON line per run to runs/bench_betweenness.jsonl.
"""

from __future__ import annotations

import argparse
import json
import platform
import time
from pathlib import Path

import networkx as nx

from road_agents.graph import load_graph, to_simple_digraph
from road_agents.tools import edge_criticality

RUNS = Path(__file__).resolve().parents[1] / "runs"


def top_overlap(a: dict, b: dict, n: int) -> float:
    ta = {e for e, _ in sorted(a.items(), key=lambda x: -x[1])[:n]}
    tb = {e for e, _ in sorted(b.items(), key=lambda x: -x[1])[:n]}
    return len(ta & tb) / n


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("city")
    p.add_argument("--k", type=int, nargs="*", default=[100, 500, 2000])
    p.add_argument("--exact", action="store_true")
    p.add_argument("--seed", type=int, default=42)
    a = p.parse_args()

    t = time.perf_counter()
    G = load_graph(a.city)
    t_load = time.perf_counter() - t
    D = to_simple_digraph(G)
    base = {
        "city": a.city,
        "nodes": G.number_of_nodes(),
        "edges_multi": G.number_of_edges(),
        "edges_simple": D.number_of_edges(),
        "load_cached_s": round(t_load, 2),
        "machine": platform.machine(),
        "networkx": nx.__version__,
    }
    print(base, flush=True)
    RUNS.mkdir(exist_ok=True)
    results = {}
    for k in sorted(a.k) + (["exact"] if a.exact else []):
        kk = None if k == "exact" else k
        t = time.perf_counter()
        results[k] = edge_criticality(D, k=kk, seed=a.seed)
        row = {**base, "k": k, "seconds": round(time.perf_counter() - t, 1)}
        if "exact" in results and k == "exact":
            for ks in a.k:
                row[f"top100_overlap_k{ks}"] = top_overlap(results[ks], results["exact"], 100)
        print(row, flush=True)
        with open(RUNS / "bench_betweenness.jsonl", "a") as f:
            f.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    main()
