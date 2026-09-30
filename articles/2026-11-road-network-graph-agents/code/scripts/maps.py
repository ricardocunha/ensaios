"""Two static maps from the per-section table (aggregated data only).

1. Top sections by criticality (sampled edge betweenness, flow x length).
2. Pothole-request density per section (smoothed distinct locations per km).

Reads ``data/<city>-sections.csv`` and ``data/<city>-section-edges.csv``
(written by ``section_pipeline.py``). Every figure carries the OSM
attribution. No request point is drawn.

Usage:
    uv run python scripts/maps.py belo-horizonte --out ../figures
"""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import shapely  # noqa: E402
from matplotlib.collections import LineCollection  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from road_agents.graph import DATA_DIR, load_graph, slugify, to_simple_digraph  # noqa: E402
from road_agents.potholes import METRIC_CRS  # noqa: E402

# Sequential blue ramp (light -> dark) and neutrals.
BLUE = ["#b7d3f6", "#6da7ec", "#2a78d6", "#1c5cab", "#0d366b"]
BASE = "#d9d8d4"
INK = "#2b2b28"
MUTED = "#6b6a66"
ATTRIBUTION = "Road data © OpenStreetMap contributors (ODbL). openstreetmap.org/copyright"


def section_lines(city: str) -> gpd.GeoDataFrame:
    D = to_simple_digraph(load_graph(city))
    se = pd.read_csv(DATA_DIR / f"{slugify(city)}-section-edges.csv")
    geoms, sids = [], []
    seen = set()
    for sid, u, v in se.itertuples(index=False):
        key = (min(u, v), max(u, v))
        if key in seen:  # draw each two-way link once
            continue
        seen.add(key)
        data = D[u][v]
        g = data.get("geometry") or shapely.LineString(
            [(D.nodes[u]["x"], D.nodes[u]["y"]), (D.nodes[v]["x"], D.nodes[v]["y"])]
        )
        geoms.append(g)
        sids.append(sid)
    return gpd.GeoDataFrame({"section_id": sids}, geometry=geoms, crs="EPSG:4326").to_crs(METRIC_CRS)


def segments(gdf: gpd.GeoDataFrame) -> list[np.ndarray]:
    return [np.asarray(g.coords)[:, :2] for g in gdf.geometry]


def base_axes(title: str, subtitle: str):
    fig, ax = plt.subplots(figsize=(6.4, 7.6), dpi=110)
    fig.patch.set_facecolor("white")
    ax.set_axis_off()
    ax.set_aspect("equal")
    fig.text(0.04, 0.965, title, fontsize=12.5, color=INK, weight="bold", va="top")
    fig.text(0.04, 0.93, subtitle, fontsize=8.5, color=MUTED, va="top")
    fig.text(0.04, 0.018, ATTRIBUTION, fontsize=7, color=MUTED)
    return fig, ax


def draw(ax, gdf, color, width, z):
    ax.add_collection(LineCollection(segments(gdf), colors=color, linewidths=width, zorder=z, capstyle="round"))


def map_criticality(lines, table, out: Path, k: int, top: int = 100):
    ranked = table.sort_values(["betweenness_mean", "section_id"], ascending=[False, True])
    tiers = [(ranked.head(10), BLUE[4], 2.6, "Top 10"), (ranked.iloc[10:top], BLUE[2], 1.6, f"11–{top}")]
    fig, ax = base_axes(
        f"Most critical road sections, Belo Horizonte (top {top} of {len(table):,})",
        f"Travel-time edge betweenness (k={k} sampled sources), flow of both directions,\n"
        "length-weighted mean per section",
    )
    draw(ax, lines, BASE, 0.25, 1)
    handles = []
    for z, (rows, color, w, label) in enumerate(reversed(tiers), 2):
        draw(ax, lines[lines["section_id"].isin(rows["section_id"])], color, w, z)
    for rows, color, w, label in tiers:
        handles.append(Line2D([], [], color=color, lw=w + 0.6, label=label))
    handles.append(Line2D([], [], color=BASE, lw=1.5, label="Other sections"))
    ax.autoscale_view()
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=8, labelcolor=INK)
    fig.subplots_adjust(left=0.02, right=0.98, top=0.9, bottom=0.05)
    fig.savefig(out, dpi=110)
    plt.close(fig)


def map_density(lines, table, out: Path, window: str):
    has = table[table["request_points"] > 0]
    # Classes by quintile of the smoothed rate among sections with requests.
    q = has["smoothed_rate_per_km"].quantile([0.2, 0.4, 0.6, 0.8]).to_numpy()
    cls = np.searchsorted(q, has["smoothed_rate_per_km"].to_numpy(), side="right")
    fig, ax = base_axes(
        "Pothole-repair requests per km, Belo Horizonte",
        f"Tapa-Buraco requests ({window}), distinct locations per km per road section,\n"
        "smoothed. Shows where repairs are requested, not measured pavement condition.",
    )
    draw(ax, lines, BASE, 0.25, 1)
    edges = [has["smoothed_rate_per_km"].min(), *q, has["smoothed_rate_per_km"].max()]
    handles = []
    for c in range(5):
        ids = has["section_id"][cls == c]
        draw(ax, lines[lines["section_id"].isin(ids)], BLUE[c], 0.45 + 0.1 * c, 2 + c)
        handles.append(Line2D([], [], color=BLUE[c], lw=2, label=f"{edges[c]:.1f}–{edges[c + 1]:.1f}"))
    handles.append(Line2D([], [], color=BASE, lw=1.5, label="No request"))
    ax.autoscale_view()
    ax.legend(
        handles=handles, loc="lower right", frameon=False, fontsize=8, labelcolor=INK,
        title="Locations per km (quintiles)", title_fontsize=8,
    )
    fig.subplots_adjust(left=0.02, right=0.98, top=0.9, bottom=0.05)
    fig.savefig(out, dpi=110)
    plt.close(fig)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("city", nargs="?", default="belo-horizonte")
    p.add_argument("--k", type=int, default=2000)
    p.add_argument("--window", default="Aug 2022 – Jul 2023")
    p.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[2] / "figures")
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    table = pd.read_csv(DATA_DIR / f"{slugify(a.city)}-sections.csv")
    lines = section_lines(a.city)
    map_criticality(lines, table, a.out / "bh-critical-sections.png", a.k)
    map_density(lines, table, a.out / "bh-pothole-density.png", a.window)
    for f in sorted(a.out.glob("bh-*.png")):
        print(f, f.stat().st_size)


if __name__ == "__main__":
    main()
