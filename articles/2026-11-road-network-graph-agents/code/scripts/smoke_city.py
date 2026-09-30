"""Run every tool once on a real city and print timings.

Usage:
    uv run python scripts/smoke_city.py porto-alegre --k 500 --pairs 1000
"""

from __future__ import annotations

import argparse
import json
import time

from road_agents.graph import load_graph, to_simple_digraph
from road_agents.pois import load_pois
from road_agents.tools import (
    accessibility,
    closure_impact,
    compute_baseline,
    edge_criticality,
    sample_od_pairs,
    snap_points,
    top_edges,
)


class Timer:
    def __init__(self):
        self.t = time.perf_counter()

    def lap(self) -> float:
        now = time.perf_counter()
        dt, self.t = now - self.t, now
        return round(dt, 2)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("city")
    p.add_argument("--k", type=int, default=500)
    p.add_argument("--pairs", type=int, default=1000)
    p.add_argument("--top", type=int, default=5)
    a = p.parse_args()

    out: dict = {"city": a.city, "k": a.k, "pairs": a.pairs}
    tm = Timer()
    D = to_simple_digraph(load_graph(a.city))
    out["load_s"] = tm.lap()
    out["nodes"], out["edges"] = D.number_of_nodes(), D.number_of_edges()

    for kind in ("hospital", "school"):
        pois = load_pois(a.city, kind)
        nodes = snap_points(D, [(r["lon"], r["lat"]) for r in pois])
        out[f"{kind}_pois"] = len(pois)
        out[f"{kind}_access"] = accessibility(D, nodes)
        out[f"{kind}_s"] = tm.lap()

    scores = edge_criticality(D, k=a.k)
    out["criticality_s"] = tm.lap()
    pairs = sample_od_pairs(D, a.pairs)
    base = compute_baseline(D, pairs)
    out["baseline_s"] = tm.lap()
    out["closures"] = []
    for (u, v), score in top_edges(scores, a.top):
        imp = closure_impact(D, [(u, v)], base).to_dict()
        imp["name"] = D[u][v].get("name")
        imp["betweenness"] = score
        out["closures"].append(imp)
    out["closures_s"] = tm.lap()
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
