"""Road sections: chains of OSM edges that a maintenance crew would treat as one job.

Merge rule (docs/DATA.md): links (both directions of a street) chain while they
are the same road (name or ``ref``, base class) with no fork, break at a strictly
higher-class road and are cut into pieces of at most ``max_length_m``; unnamed links never merge.
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from road_agents.graph import DATA_DIR, slugify

Edge = tuple[int, int]
Link = tuple[int, int]  # undirected, stored as (min, max)

# Higher rank = more important road. Links (ramps) and odd classes rank 0.
HIGHWAY_RANK = {
    "motorway": 6,
    "trunk": 5,
    "primary": 4,
    "secondary": 3,
    "tertiary": 2,
    "unclassified": 1,
    "residential": 1,
    "living_street": 1,
    "busway": 1,
}


def _as_list(x) -> list:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return []
    return list(x) if isinstance(x, (list, tuple, set)) else [x]


def highway_class(data: dict) -> str:
    """One highway class per edge: the highest-ranked of OSM's (possibly
    multiple) values; ``*_link`` classes keep their suffix."""
    values = [str(h) for h in _as_list(data.get("highway"))] or ["unknown"]
    return max(values, key=lambda h: (HIGHWAY_RANK.get(h, 0), h))


def rank(hwy: str) -> int:
    return HIGHWAY_RANK.get(hwy, 0)


def road_names(data: dict) -> frozenset[str]:
    """The names an edge answers to: its ``name`` values, else its ``ref``s."""
    names = [str(n).strip() for n in _as_list(data.get("name")) if str(n).strip()]
    if not names:
        names = [str(r).strip() for r in _as_list(data.get("ref")) if str(r).strip()]
    return frozenset(names)


@dataclass
class LinkInfo:
    link: Link
    edges: list[Edge]  # directed edges of D in this link (1 or 2)
    names: frozenset[str]
    highway: str
    length_m: float


@dataclass
class Section:
    section_id: str
    name: str  # most common name by length ("" if unnamed)
    highway: str
    links: list[Link]  # in chain order
    edges: list[Edge]  # all directed edges of D in the section
    length_m: float  # sum of link lengths (one direction)
    oneway: bool  # every link is one-way


def _link_infos(D: nx.DiGraph) -> dict[Link, LinkInfo]:
    infos: dict[Link, LinkInfo] = {}
    for u, v in sorted(D.edges):
        if u == v:
            continue
        key = (min(u, v), max(u, v))
        if key in infos:
            infos[key].edges.append((u, v))
            continue
        data = D[key[0]][key[1]] if D.has_edge(*key) else D[u][v]
        infos[key] = LinkInfo(
            key, [(u, v)], road_names(data), highway_class(data), float(data.get("length", 0.0))
        )
    return infos


def _same_road(a: LinkInfo, b: LinkInfo) -> bool:
    return bool(a.names) and a.highway == b.highway and not a.names.isdisjoint(b.names)


def _continues(n: int, a: LinkInfo, b: LinkInfo, at: dict[int, list[LinkInfo]]) -> bool:
    """Does the section pass through node ``n`` from link ``a`` to link ``b``?"""
    if not _same_road(a, b):
        return False
    here = at[n]
    if [x.link for x in here if x.link != a.link and _same_road(a, x)] != [b.link]:
        return False
    if [x.link for x in here if x.link != b.link and _same_road(b, x)] != [a.link]:
        return False
    r = rank(a.highway)
    return not any(
        rank(x.highway) > r and not _same_road(a, x) for x in here if x.link not in (a.link, b.link)
    )


def _chains(infos: dict[Link, LinkInfo]) -> list[list[Link]]:
    at: dict[int, list[LinkInfo]] = defaultdict(list)
    for info in infos.values():
        for n in info.link:
            at[n].append(info)

    # next_link[(link, node)] = the link the section continues into through node
    nxt: dict[tuple[Link, int], Link] = {}
    for n, here in at.items():
        for a in here:
            for b in here:
                if a.link < b.link and _continues(n, a, b, at):
                    nxt[(a.link, n)] = b.link
                    nxt[(b.link, n)] = a.link

    seen: set[Link] = set()
    chains: list[list[Link]] = []

    def walk(start: Link, via: int) -> list[Link]:
        """Links after ``start`` leaving through node ``via``."""
        out, cur, node = [], start, via
        while (cur, node) in nxt:
            b = nxt[(cur, node)]
            if b in seen:
                break
            seen.add(b)
            out.append(b)
            node = b[0] if b[1] == node else b[1]
            cur = b
        return out

    # Start from links with an open end first, so open chains are walked end to end.
    order = sorted(infos, key=lambda lk: (all((lk, n) in nxt for n in lk), lk))
    for lk in order:
        if lk in seen:
            continue
        seen.add(lk)
        forward = walk(lk, lk[1])
        backward = walk(lk, lk[0])
        chains.append(list(reversed(backward)) + [lk] + forward)
    return chains


def _split(chain: list[Link], infos: dict[Link, LinkInfo], max_length_m: float | None) -> list[list[Link]]:
    total = sum(infos[lk].length_m for lk in chain)
    if not max_length_m or total <= max_length_m or len(chain) == 1:
        return [chain]
    parts = min(len(chain), math.ceil(total / max_length_m))
    target = total / parts
    out: list[list[Link]] = [[] for _ in range(parts)]
    acc = 0.0
    for lk in chain:  # each link goes to the piece that holds its midpoint
        L = infos[lk].length_m
        out[min(parts - 1, int((acc + L / 2) // target))].append(lk)
        acc += L
    return [p for p in out if p]


def build_sections(D: nx.DiGraph, max_length_m: float | None = 1000.0) -> list[Section]:
    """Group the edges of ``D`` into sections (see module docstring). Every directed
    edge except self-loops is in exactly one section; ids ``S00001``, ... are deterministic."""
    infos = _link_infos(D)
    pieces = [p for ch in _chains(infos) for p in _split(ch, infos, max_length_m)]

    def display_name(links: list[Link]) -> str:
        by_len: dict[str, float] = defaultdict(float)
        for lk in links:
            for nm in infos[lk].names:
                by_len[nm] += infos[lk].length_m
        return max(sorted(by_len), key=lambda nm: by_len[nm]) if by_len else ""

    rows = []
    for links in pieces:
        rows.append((display_name(links), infos[links[0]].highway, min(links), links))
    rows.sort(key=lambda r: (r[0] == "", r[0], r[1], r[2]))
    sections = []
    for i, (name, hwy, _, links) in enumerate(rows, 1):
        edges = [e for lk in links for e in infos[lk].edges]
        sections.append(
            Section(
                section_id=f"S{i:05d}",
                name=name,
                highway=hwy,
                links=links,
                edges=edges,
                length_m=sum(infos[lk].length_m for lk in links),
                oneway=all(len(infos[lk].edges) == 1 for lk in links),
            )
        )
    return sections


def edge_to_section(sections: Iterable[Section]) -> dict[Edge, str]:
    return {e: s.section_id for s in sections for e in s.edges}


def link_to_section(sections: Iterable[Section]) -> dict[Link, str]:
    return {lk: s.section_id for s in sections for lk in s.links}


def section_criticality(
    D: nx.DiGraph, sections: Iterable[Section], scores: dict[Edge, float]
) -> dict[str, dict[str, float]]:
    """Aggregate edge betweenness per section. A link's flow sums both directions;
    ``max`` = highest link flow, ``mean`` = length-weighted mean (the criticality we rank by)."""
    out = {}
    for s in sections:
        flows, lengths = [], []
        for u, v in s.links:
            flows.append(scores.get((u, v), 0.0) + scores.get((v, u), 0.0))
            lengths.append(float(D[u][v]["length"]) if D.has_edge(u, v) else float(D[v][u]["length"]))
        total = sum(lengths)
        mean = sum(f * L for f, L in zip(flows, lengths)) / total if total > 0 else max(flows)
        out[s.section_id] = {"max": max(flows), "mean": mean}
    return out


# --- betweenness cache -----------------------------------------------------


def betweenness_cache_path(place: str, k: int | None, seed: int = 42, data_dir: Path | None = None) -> Path:
    tag = "exact" if k is None else f"k{k}-seed{seed}"
    return (data_dir or DATA_DIR) / f"{slugify(place)}-betweenness-{tag}.csv"


def save_scores(scores: dict[Edge, float], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["u", "v", "betweenness"])
        for (u, v), s in sorted(scores.items()):
            w.writerow([u, v, repr(float(s))])


def load_scores(path: Path) -> dict[Edge, float]:
    with open(path, newline="") as f:
        return {(int(r["u"]), int(r["v"])): float(r["betweenness"]) for r in csv.DictReader(f)}
