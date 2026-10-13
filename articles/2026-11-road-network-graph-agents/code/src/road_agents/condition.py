"""Per-section condition score and a synthetic repair cost.

Condition comes from Tapa-Buraco request density (see ``potholes.py``): it
measures *reporting*, not only pavement state. The repair cost is synthetic,
not a price. Every assumption is a module constant so the article can quote it.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from road_agents.sections import Section

# Empirical-Bayes smoothing of request density: a section behaves as if it had
# PRIOR_KM extra km at the network-wide rate. Stops a 20 m section with one
# request from outranking a 1 km section with twenty.
PRIOR_KM = 0.5

# Lanes when OSM has no ``lanes`` tag, for two-way sections (both directions)
# and one-way sections. Assumption, not measured.
DEFAULT_LANES_TWO_WAY = {"motorway": 4, "trunk": 4, "primary": 4, "secondary": 2, "tertiary": 2}
DEFAULT_LANES_ONE_WAY = {"motorway": 2, "trunk": 2, "primary": 2, "secondary": 2}
FALLBACK_LANES_TWO_WAY = 2
FALLBACK_LANES_ONE_WAY = 1
LANE_WIDTH_M = 3.5

# Repair cost = area_m2 * UNIT_COST * (SEVERITY_MIN + (1 - SEVERITY_MIN) * condition).
# condition 0 -> spot patching (30% of full cost); condition 1 -> full milling
# and overlay. Cost unit = 1 m2 of full resurfacing (no currency).
UNIT_COST = 1.0
SEVERITY_MIN = 0.3


def _lanes_of(value) -> float | None:
    vals = value if isinstance(value, (list, tuple)) else [value]
    nums = []
    for v in vals:
        try:
            nums.append(float(str(v).split(";")[0]))
        except (TypeError, ValueError):
            continue
    nums = [n for n in nums if n > 0]
    return max(nums) if nums else None


def section_lanes(D, s: Section) -> float:
    """Length-weighted mean of OSM ``lanes`` over the section's edges that
    have it (a two-way link counts both directions' tags, as OSM's ``lanes``
    on a two-way way is the total); default by class otherwise."""
    tagged, weight = 0.0, 0.0
    for u, v in s.links:
        data = D[u][v] if D.has_edge(u, v) else D[v][u]
        n = _lanes_of(data.get("lanes"))
        if n is not None:
            L = float(data.get("length", 0.0))
            tagged += n * L
            weight += L
    if weight > 0:
        return tagged / weight
    base = s.highway.removesuffix("_link")
    if s.oneway:
        return DEFAULT_LANES_ONE_WAY.get(base, FALLBACK_LANES_ONE_WAY)
    return DEFAULT_LANES_TWO_WAY.get(base, FALLBACK_LANES_TWO_WAY)


def smoothed_rate(counts: np.ndarray, length_km: np.ndarray, prior_km: float = PRIOR_KM) -> np.ndarray:
    """Posterior-mean requests per km under a Gamma prior centred on the
    network rate: ``(n + r * prior_km) / (L + prior_km)``."""
    counts = np.asarray(counts, float)
    length_km = np.asarray(length_km, float)
    r = counts.sum() / length_km.sum() if length_km.sum() > 0 else 0.0
    return (counts + r * prior_km) / (length_km + prior_km)


def condition_score(counts: np.ndarray, rate: np.ndarray) -> np.ndarray:
    """0 for sections with no requests (no evidence of damage); otherwise
    the percentile rank (0, 1] of the smoothed rate among sections with at
    least one request. Ties get the average rank."""
    counts = np.asarray(counts)
    out = np.zeros(len(counts))
    has = counts > 0
    if has.any():
        out[has] = pd.Series(np.asarray(rate)[has]).rank(method="average", pct=True).to_numpy()
    return out


def repair_cost(area_m2: np.ndarray, condition: np.ndarray) -> np.ndarray:
    return np.asarray(area_m2) * UNIT_COST * (SEVERITY_MIN + (1 - SEVERITY_MIN) * np.asarray(condition))


def section_table(
    D,
    sections: Iterable[Section],
    criticality: dict[str, dict[str, float]],
    requests: dict[str, int],
    points: dict[str, int],
) -> pd.DataFrame:
    """The tidy per-section table the agents read. The score uses ``points``
    (distinct request locations), so repeat reports at one address count once.
    ``value = condition * criticality * length_km``."""
    rows = []
    for s in sections:
        lanes = section_lanes(D, s)
        c = criticality[s.section_id]
        rows.append(
            {
                "section_id": s.section_id,
                "name": s.name,
                "highway": s.highway,
                "oneway": s.oneway,
                "n_edges": len(s.edges),
                "length_m": round(s.length_m, 1),
                "lanes": round(lanes, 2),
                "area_m2": round(s.length_m * lanes * LANE_WIDTH_M, 1),
                "betweenness_max": c["max"],
                "betweenness_mean": c["mean"],
                "requests": int(requests.get(s.section_id, 0)),
                "request_points": int(points.get(s.section_id, 0)),
            }
        )
    df = pd.DataFrame(rows)
    km = df["length_m"] / 1000
    df["points_per_km"] = np.where(km > 0, df["request_points"] / km.where(km > 0, 1), 0.0)
    df["smoothed_rate_per_km"] = smoothed_rate(df["request_points"], km)
    df["condition"] = condition_score(df["request_points"], df["smoothed_rate_per_km"])
    top = df["betweenness_mean"].max()
    df["criticality"] = df["betweenness_mean"] / top if top > 0 else 0.0
    df["repair_cost"] = repair_cost(df["area_m2"], df["condition"])
    df["value"] = df["condition"] * df["criticality"] * km
    return df


def describe(values: pd.Series) -> dict[str, float]:
    v = values.to_numpy(float)
    return {
        "mean": float(v.mean()),
        "median": float(np.median(v)),
        "p90": float(np.percentile(v, 90)),
        "p99": float(np.percentile(v, 99)),
        "max": float(v.max()),
    }


def gini(values: Iterable[float]) -> float:
    """Gini coefficient of non-negative values (0 = even, 1 = concentrated)."""
    v = np.sort(np.asarray(list(values), float))
    n = len(v)
    if n == 0 or v.sum() == 0:
        return 0.0
    cum = np.cumsum(v)
    return float((n + 1 - 2 * (cum / cum[-1]).sum()) / n)

