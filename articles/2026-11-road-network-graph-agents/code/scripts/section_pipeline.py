"""Milestone 2: sections, pothole snapping, condition score, knapsack baseline.

Needs the cached graph and a cached betweenness CSV
(``scripts/cache_betweenness.py``). Writes, all git-ignored:

- ``data/<city>-sections.csv``        tidy per-section table (the agents read this)
- ``data/<city>-section-edges.csv``   section_id -> directed edges (u, v)
- ``runs/m2-<city>-k<k>.json``         every number reported in docs/RESULTS.md

No per-request data is written: coordinates are snapped in memory and only
per-section counts leave this script.

Usage:
    nice uv run python scripts/section_pipeline.py belo-horizonte --k 2000
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from road_agents import baseline
from road_agents.condition import describe, gini, section_table
from road_agents.graph import DATA_DIR, load_graph, slugify, to_simple_digraph
from road_agents.potholes import links_frame, load_requests, snap_requests
from road_agents.sections import (
    betweenness_cache_path,
    build_sections,
    link_to_section,
    load_scores,
    section_criticality,
)
from road_agents.tools import closure_impact, compute_baseline, sample_od_pairs, top_edges

RUNS = Path(__file__).resolve().parents[1] / "runs"
# 12 months ending July 2023 (the newest month published).
FILE_KEYS = ["2022", "2023-01", "2023-02", "2023-03", "2023-04", "2023-05", "2023-06", "2023-07"]
START, END = "2022-08-01", "2023-07-31"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("city", nargs="?", default="belo-horizonte")
    p.add_argument("--k", type=int, default=2000)
    p.add_argument("--max-length", type=float, default=1000.0)
    p.add_argument("--snap-m", type=float, default=30.0)
    p.add_argument("--pairs", type=int, default=1000)
    p.add_argument("--closures", type=int, default=10, help="top-N sections/edges to close")
    p.add_argument("--compare-k", type=int, default=500, help="also rank sections with this cached k")
    p.add_argument("--budgets", type=float, nargs="+", default=[0.05, 0.10, 0.20])
    a = p.parse_args()
    out: dict = {"city": a.city, "k": a.k, "max_length_m": a.max_length, "snap_m": a.snap_m}
    t0 = time.perf_counter()

    D = to_simple_digraph(load_graph(a.city))
    out["graph"] = {"nodes": D.number_of_nodes(), "edges": D.number_of_edges(), "self_loops": nx_self_loops(D)}

    # --- sections ------------------------------------------------------------
    t = time.perf_counter()
    sections = build_sections(D, max_length_m=a.max_length)
    out["sections_s"] = round(time.perf_counter() - t, 2)
    unsplit = build_sections(D, max_length_m=None)
    L = np.array([s.length_m for s in sections])
    out["sections"] = {
        "n": len(sections),
        "n_without_length_cap": len(unsplit),
        "edges_covered": sum(len(s.edges) for s in sections),
        "links": sum(len(s.links) for s in sections),
        "unnamed": sum(1 for s in sections if not s.name),
        "oneway": sum(1 for s in sections if s.oneway),
        "km": float(L.sum() / 1000),
        "length_m": {"median": float(np.median(L)), "p90": float(np.percentile(L, 90)), "max": float(L.max())},
        "edges_per_section": {
            "mean": float(np.mean([len(s.edges) for s in sections])),
            "max": int(max(len(s.edges) for s in sections)),
        },
        "by_highway": dict(Counter(s.highway for s in sections).most_common()),
    }
    by_id = {s.section_id: s for s in sections}

    # --- criticality per section, top-10 edges vs sections -------------------
    scores = load_scores(betweenness_cache_path(a.city, a.k))
    crit = section_criticality(D, sections, scores)
    ranked = sorted(crit, key=lambda sid: (-crit[sid]["mean"], sid))
    edge_sec = {e: s.section_id for s in sections for e in s.edges}
    pairs = sample_od_pairs(D, a.pairs)
    t = time.perf_counter()
    base = compute_baseline(D, pairs)
    out["od_baseline_s"] = round(time.perf_counter() - t, 2)

    def impact(edges) -> dict:
        imp = closure_impact(D, edges, base)
        return {
            "affected": imp.n_affected,
            "disconnected": imp.n_disconnected,
            "mean_delay_s": round(imp.mean_delay_s, 1),
            "max_delay_s": round(imp.max_delay_s, 1),
            "total_delay_s": round(imp.total_delay_s, 1),
        }

    t = time.perf_counter()
    top_e = []
    for (u, v), sc in top_edges(scores, a.closures):
        top_e.append(
            {"edge": [u, v], "name": str(D[u][v].get("name")), "betweenness": sc,
             "section_id": edge_sec.get((u, v)), **impact([(u, v)])}
        )
    top_s = []
    for sid in ranked[: a.closures]:
        s = by_id[sid]
        top_s.append(
            {"section_id": sid, "name": s.name, "highway": s.highway, "length_m": round(s.length_m, 1),
             "n_edges": len(s.edges), "criticality_mean": crit[sid]["mean"], "criticality_max": crit[sid]["max"],
             **impact(s.edges)}
        )
    # the best section of each named road: the top-10 *roads*
    top_r, names_seen = [], set()
    for sid in ranked:
        s = by_id[sid]
        if not s.name or s.name in names_seen:
            continue
        names_seen.add(s.name)
        top_r.append(
            {"section_id": sid, "name": s.name, "highway": s.highway, "length_m": round(s.length_m, 1),
             "criticality_mean": crit[sid]["mean"], **impact(s.edges)}
        )
        if len(top_r) == a.closures:
            break
    out["top_roads"] = top_r
    out["closures_s"] = round(time.perf_counter() - t, 2)
    alt = betweenness_cache_path(a.city, a.compare_k)
    if a.compare_k and alt.exists():
        crit_alt = section_criticality(D, sections, load_scores(alt))
        ranked_alt = sorted(crit_alt, key=lambda sid: (-crit_alt[sid]["mean"], sid))
        out["compare_k"] = {
            "k": a.compare_k,
            **{f"top{n}_section_overlap": len(set(ranked[:n]) & set(ranked_alt[:n])) / n for n in (10, 100, 1000)},
        }
    out["top_edges"] = top_e
    out["top_sections"] = top_s
    out["top10_distinct"] = {
        "edge_names": len({e["name"] for e in top_e}),
        "edge_sections": len({e["section_id"] for e in top_e}),
        "section_names": len({s["name"] for s in top_s}),
    }

    # --- pothole requests ------------------------------------------------------
    t = time.perf_counter()
    req = load_requests(FILE_KEYS, START, END)
    out["requests_load_s"] = round(time.perf_counter() - t, 2)
    has = req["lat"].notna() & req["lon"].notna()
    month = req["created"].dt.to_period("M").astype(str)
    out["requests"] = {
        "window": [START, END],
        "n": len(req),
        "with_coords": int(has.sum()),
        "by_month": month.value_counts().sort_index().to_dict(),
        "by_channel": req["channel"].value_counts().to_dict(),
        "by_status": req["status"].value_counts().to_dict(),
        "by_access_level": req["access_level"].value_counts().to_dict(),
        "distinct_points": int(req.loc[has, ["lat", "lon"]].round(6).drop_duplicates().shape[0]),
    }
    links = links_frame(D, link_to_section(sections))
    t = time.perf_counter()
    snap = snap_requests(req, links, max_distance_m=a.snap_m)
    out["snap_s"] = round(time.perf_counter() - t, 2)
    dist = snap["distance_m"]
    n_coords = int(has.sum())
    out["snapping"] = {
        "threshold_m": a.snap_m,
        "snapped": int(snap["section_id"].notna().sum()),
        "unsnapped_share_of_coords": float(1 - snap["section_id"].notna().sum() / n_coords),
        "distance_m": {q: float(dist.quantile(x)) for q, x in [("median", 0.5), ("p90", 0.9), ("p95", 0.95)]},
        "within_m": {str(m): float((dist <= m).sum() / n_coords) for m in (5, 10, 15, 30, 50, 100)},
        "sections_with_requests": int(snap["section_id"].nunique()),
    }
    snapped = req.loc[snap["section_id"].notna(), ["lat", "lon"]].round(6).assign(section_id=snap["section_id"].dropna())
    counts = snapped["section_id"].value_counts().to_dict()
    points = snapped.drop_duplicates().groupby("section_id").size().to_dict()
    ch = req.loc[snap["section_id"].notna(), "channel"]
    out["snapping"]["snapped_by_channel"] = ch.value_counts().to_dict()
    del req, snap, snapped  # nothing per request survives past this point

    # --- tidy table --------------------------------------------------------------
    df = section_table(D, sections, crit, counts, points)
    slug = slugify(a.city)
    df.to_csv(DATA_DIR / f"{slug}-sections.csv", index=False)
    pd.DataFrame(
        [(s.section_id, u, v) for s in sections for u, v in s.edges], columns=["section_id", "u", "v"]
    ).to_csv(DATA_DIR / f"{slug}-section-edges.csv", index=False)

    with_req = df[df["request_points"] > 0]
    out["condition"] = {
        "sections_with_requests": len(with_req),
        "share_sections_with_requests": len(with_req) / len(df),
        "share_km_with_requests": float(with_req["length_m"].sum() / df["length_m"].sum()),
        "requests_snapped": int(df["requests"].sum()),
        "points_snapped": int(df["request_points"].sum()),
        "network_rate_points_per_km": float(df["request_points"].sum() / (df["length_m"].sum() / 1000)),
        "points_per_section_with_requests": describe(with_req["request_points"]),
        "smoothed_rate_with_requests": describe(with_req["smoothed_rate_per_km"]),
        "gini_points_all_sections": gini(df["request_points"]),
        "share_points_top10pct_sections": top_share(df["request_points"], 0.10),
        "by_highway": df.groupby("highway").apply(
            lambda g: {"sections": len(g), "km": float(g["length_m"].sum() / 1000),
                       "points_per_km": float(g["request_points"].sum() / (g["length_m"].sum() / 1000)),
                       "share_with_requests": float((g["request_points"] > 0).mean())},
            include_groups=False,
        ).to_dict(),
        "spearman_rate_vs_criticality": float(
            df["smoothed_rate_per_km"].rank().corr(df["criticality"].rank())
        ),
        "spearman_rate_vs_criticality_with_requests": float(
            with_req["smoothed_rate_per_km"].rank().corr(with_req["criticality"].rank())
        ),
        "total_area_m2": float(df["area_m2"].sum()),
        "total_repair_cost_candidates": float(with_req["repair_cost"].sum()),
        "lanes_tagged_share": None,  # filled below
    }
    out["condition"]["top10_condition"] = (
        with_req.sort_values(["condition", "section_id"], ascending=[False, True]).head(10)
        [["section_id", "name", "highway", "length_m", "request_points", "smoothed_rate_per_km"]].to_dict("records")
    )
    out["condition"]["lanes_tagged_share"] = float(
        sum(1 for s in sections if any(D[u][v].get("lanes") is not None if D.has_edge(u, v) else D[v][u].get("lanes") is not None for u, v in s.links))
        / len(sections)
    )

    # --- knapsack baseline ---------------------------------------------------------
    cand = df[df["value"] > 0]
    total_cost = float(cand["repair_cost"].sum())
    total_value = float(cand["value"].sum())
    out["baseline"] = {"candidates": len(cand), "total_cost": total_cost, "total_value": total_value, "runs": []}
    for share in a.budgets:
        budget = share * total_cost
        row = {"budget_share": share, "budget": budget}
        chosen = {}
        for fn in (baseline.greedy, baseline.exact):
            t = time.perf_counter()
            plan = fn(cand["section_id"], cand["value"], cand["repair_cost"], budget)
            sel = cand[cand["section_id"].isin(plan.chosen)]
            chosen[fn.__name__] = set(plan.chosen)
            row[fn.__name__] = {
                "method": plan.method,
                "seconds": round(time.perf_counter() - t, 3),
                "n": len(plan.chosen),
                "km": float(sel["length_m"].sum() / 1000),
                "value": plan.total_value,
                "value_share": plan.total_value / total_value,
                "cost": plan.total_cost,
                "requests_covered": int(sel["requests"].sum()),
                "requests_covered_share": float(sel["requests"].sum() / df["requests"].sum()),
                "top_names": sel.sort_values("value", ascending=False)["name"].head(5).tolist(),
            }
        g, e = row["greedy"], row["exact"]
        row["greedy_gap"] = 1 - g["value"] / e["value"] if e["value"] else 0.0
        gs, es = chosen["greedy"], chosen["exact"]
        row["jaccard"] = len(gs & es) / len(gs | es) if gs | es else 1.0
        out["baseline"]["runs"].append(row)

    out["total_s"] = round(time.perf_counter() - t0, 1)
    RUNS.mkdir(exist_ok=True)
    path = RUNS / f"m2-{slug}-k{a.k}.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))


def nx_self_loops(D) -> int:
    return sum(1 for u, v in D.edges if u == v)


def top_share(values: pd.Series, frac: float) -> float:
    v = np.sort(values.to_numpy(float))[::-1]
    n = max(1, int(round(frac * len(v))))
    return float(v[:n].sum() / v.sum()) if v.sum() else 0.0


if __name__ == "__main__":
    main()
