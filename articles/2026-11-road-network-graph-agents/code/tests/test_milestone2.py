"""Sections, pothole requests, condition score and the knapsack baseline.
Synthetic inputs only; no network access."""

from __future__ import annotations

import itertools
import random

import networkx as nx
import numpy as np
import pytest

from road_agents import baseline
from road_agents.condition import (
    LANE_WIDTH_M,
    SEVERITY_MIN,
    condition_score,
    gini,
    repair_cost,
    section_lanes,
    section_table,
    smoothed_rate,
)
from road_agents.potholes import links_frame, read_requests, snap_requests
from road_agents.sections import (
    build_sections,
    edge_to_section,
    highway_class,
    link_to_section,
    load_scores,
    road_names,
    save_scores,
    section_criticality,
)

# ~1 m in degrees of longitude at BH's latitude (-19.9) is 1 / 104_700.
LON0, LAT0, DEG_PER_M = -43.95, -19.92, 1 / 104_700


def road(D, u, v, name, hwy, length=100.0, oneway=False, **extra):
    attrs = {"name": name, "highway": hwy, "length": length, "travel_time": length / 10, **extra}
    D.add_edge(u, v, **attrs)
    if not oneway:
        D.add_edge(v, u, **attrs)


@pytest.fixture
def city() -> nx.DiGraph:
    """An avenue 0-1-2-3-4 (tertiary) crossed by:
    - a primary road at node 1 (breaks the avenue),
    - a residential street at node 3 (does not break it).
    The residential street 10-3-11 runs through the avenue? No: the avenue
    is higher class, so the residential street breaks at 3.
    A residential street 20-21-22-23 has a residential crossing at 21
    (continues) and forks at 22 (breaks). One unnamed link 23-24.

        10          5
        |           |
    0 - 1 - 2 - 3 - 4          20 - 21 - 22 - 23 - 24 (unnamed)
        |       |                   |     \\
        6       11                 30      25 (same name as 22-23: fork)
    """
    D = nx.DiGraph()
    for u, v in [(0, 1), (1, 2), (2, 3), (3, 4)]:
        road(D, u, v, "Avenida A", "tertiary")
    road(D, 10, 1, "Avenida P", "primary")
    road(D, 1, 6, "Avenida P", "primary")
    road(D, 3, 11, "Rua R", "residential")
    road(D, 4, 5, "Rua S", "residential")
    for u, v in [(20, 21), (21, 22), (22, 23)]:
        road(D, u, v, "Rua T", "residential")
    road(D, 21, 30, "Rua U", "residential")
    road(D, 22, 25, "Rua T", "residential")
    road(D, 23, 24, None, "residential")
    for i, n in enumerate(sorted(D.nodes)):
        D.nodes[n]["x"] = LON0 + 0.001 * i
        D.nodes[n]["y"] = LAT0
    return D


def by_name(sections, name):
    return sorted((s for s in sections if s.name == name), key=lambda s: s.links)


# --- sections ------------------------------------------------------------------


def test_every_edge_in_exactly_one_section(city):
    sections = build_sections(city)
    edges = [e for s in sections for e in s.edges]
    assert len(edges) == len(set(edges)) == city.number_of_edges()


def test_higher_class_road_breaks_a_section_lower_does_not(city):
    avenue = by_name(build_sections(city), "Avenida A")
    assert [s.links for s in avenue] == [[(0, 1)], [(1, 2), (2, 3), (3, 4)]]
    assert avenue[1].length_m == 300.0


def test_same_class_crossing_continues_fork_breaks(city):
    rua_t = by_name(build_sections(city), "Rua T")
    # 20-21-22 run through the Rua U crossing at 21; the fork at 22 breaks it.
    assert sorted(len(s.links) for s in rua_t) == [1, 1, 2]
    assert [(20, 21), (21, 22)] in [s.links for s in rua_t]


def test_lower_class_street_breaks_at_higher_class_road(city):
    rua_r = by_name(build_sections(city), "Rua R")
    assert [s.links for s in rua_r] == [[(3, 11)]]


def test_unnamed_links_are_own_sections(city):
    road(city, 24, 26, None, "residential")
    unnamed = [s for s in build_sections(city) if s.name == ""]
    assert len(unnamed) == 2


def test_both_directions_share_a_section_and_oneway_flag(city):
    road(city, 4, 40, "Rua O", "residential", oneway=True)
    road(city, 40, 41, "Rua O", "residential", oneway=True)
    sections = build_sections(city)
    e2s = edge_to_section(sections)
    assert e2s[(1, 2)] == e2s[(2, 1)]
    rua_o = by_name(sections, "Rua O")
    assert len(rua_o) == 1 and rua_o[0].oneway and len(rua_o[0].edges) == 2
    assert not by_name(sections, "Avenida A")[1].oneway


def test_length_cap_splits_long_chains_evenly():
    D = nx.DiGraph()
    for i in range(10):
        road(D, i, i + 1, "Avenida Longa", "secondary", length=250.0)
    whole = build_sections(D, max_length_m=None)
    capped = build_sections(D, max_length_m=1000.0)
    assert len(whole) == 1 and whole[0].length_m == 2500.0
    assert [s.length_m for s in capped] == [750.0, 1000.0, 750.0]
    assert sum(len(s.links) for s in capped) == 10


def test_ring_road_without_breaks_is_one_section():
    D = nx.DiGraph()
    for u, v in [(0, 1), (1, 2), (2, 3), (3, 0)]:
        road(D, u, v, "Praça Redonda", "tertiary", oneway=True)
    sections = build_sections(D, max_length_m=None)
    assert len(sections) == 1 and len(sections[0].links) == 4


def test_multi_name_edges_join_when_names_overlap():
    D = nx.DiGraph()
    road(D, 0, 1, "Anel Rodoviário", "trunk")
    road(D, 1, 2, ["Anel Rodoviário", "Rodovia Anel"], "trunk")
    road(D, 2, 3, "Rodovia Anel", "trunk")
    assert len(build_sections(D, max_length_m=None)) == 1


def test_section_ids_are_deterministic(city):
    a = [(s.section_id, s.links) for s in build_sections(city)]
    b = [(s.section_id, s.links) for s in build_sections(city.copy())]
    assert a == b
    assert a[0][0] == "S00001"


def test_highway_class_and_names():
    assert highway_class({"highway": ["residential", "tertiary"]}) == "tertiary"
    assert highway_class({}) == "unknown"
    assert road_names({"name": None, "ref": "MG-020"}) == frozenset({"MG-020"})
    assert road_names({"name": ["A", "B"]}) == frozenset({"A", "B"})


def test_section_criticality_sums_directions_and_weights_by_length():
    D = nx.DiGraph()
    road(D, 0, 1, "X", "primary", length=100.0)
    road(D, 1, 2, "X", "primary", length=300.0)
    [s] = build_sections(D, max_length_m=None)
    scores = {(0, 1): 0.1, (1, 0): 0.3, (1, 2): 0.2, (2, 1): 0.0}
    c = section_criticality(D, [s], scores)[s.section_id]
    assert c["max"] == pytest.approx(0.4)
    assert c["mean"] == pytest.approx((0.4 * 100 + 0.2 * 300) / 400)


def test_betweenness_cache_roundtrip(tmp_path):
    scores = {(1, 2): 0.125, (2, 1): 1e-9}
    save_scores(scores, tmp_path / "b.csv")
    assert load_scores(tmp_path / "b.csv") == scores


# --- pothole requests ----------------------------------------------------------

HEADER = (
    '"Id Ticket";"Nome Servico";"Data de criação (YYYY-MM-DD)";"Data de encerramento (YYYY-MM-DD)";'
    '"Fase Atual";"Situacao Atendimento Atual";"Canal Captacao";"Orgao Normatizador";"Orgao Responsavel";'
    '"Nome Logradouro";"Numero Logradouro";"Bairro";"Regional";"Coordenadas";"Ind Tp Pbh App";"Nivel Acesso"'
)


def row(ticket, service, created, coords, channel="Portal"):
    return (
        f'"{ticket}";"{service}";"{created}";"";"Encerrado";"Serviço realizado";"{channel}";"X";"Y";'
        f'"RUA A";"1";"Centro";"CENTRO-SUL";"{coords}";"Sim";"Restrito"'
    )


def test_read_requests_2022_format_latin1_iso_dates():
    text = "\r\n".join(
        [HEADER, row("a1", "Tapa-Buraco", "2022-08-03", "-19.9, -43.9"), row("a2", "Poda de Árvore", "2022-08-03", "")]
    )
    df = read_requests(text.encode("latin-1"))
    assert list(df["ticket"]) == ["a1"]
    assert str(df["created"][0].date()) == "2022-08-03"
    assert (df["lat"][0], df["lon"][0]) == (-19.9, -43.9)
    assert df["access_level"][0] == "Restrito"


def test_read_requests_2023_format_utf8_bom_dmy_dates_and_missing_coords():
    text = "\n".join(
        [HEADER, row("b1", "Tapa-Buraco", "31/05/2023", "", "Integração entre Sistemas"),
         row("b2", "Tapa-Buraco", "01/05/2023", "-19.8, -43.95")]
    )
    df = read_requests(b"\xef\xbb\xbf" + text.encode("utf-8"))
    assert [str(d.date()) for d in df["created"]] == ["2023-05-31", "2023-05-01"]
    assert np.isnan(df["lat"][0]) and df["lon"][1] == -43.95
    assert df["channel"][0] == "Integração entre Sistemas"


def test_snap_requests_threshold(city):
    import pandas as pd

    sections = build_sections(city)
    links = links_frame(city, link_to_section(sections))
    x0, x1 = city.nodes[1]["x"], city.nodes[2]["x"]  # the 1-2 link runs east-west at LAT0
    mid = (x0 + x1) / 2
    req = pd.DataFrame(
        {
            "lat": [LAT0 + 10 * DEG_PER_M, LAT0 + 100 * DEG_PER_M, np.nan],
            "lon": [mid, mid, mid],
        }
    )
    out = snap_requests(req, links, max_distance_m=30)
    assert out["section_id"][0] == edge_to_section(sections)[(1, 2)]
    assert 8 < out["distance_m"][0] < 12
    assert out["section_id"][1] is None and 90 < out["distance_m"][1] < 110
    assert out["section_id"][2] is None and np.isnan(out["distance_m"][2])


# --- condition and cost --------------------------------------------------------


def test_smoothed_rate_shrinks_short_sections_towards_network_rate():
    counts = np.array([1, 20, 0])
    km = np.array([0.02, 1.0, 1.0])
    r = smoothed_rate(counts, km, prior_km=0.5)
    network = 21 / 2.02
    assert r[0] == pytest.approx((1 + network * 0.5) / 0.52)
    assert r[1] > r[0]  # raw density would say 50/km vs 20/km
    assert r[2] == pytest.approx(network * 0.5 / 1.5)


def test_condition_score_zero_without_requests_and_ranks_the_rest():
    c = condition_score(np.array([0, 3, 1, 2]), np.array([5.0, 3.0, 1.0, 2.0]))
    assert list(c) == pytest.approx([0.0, 1.0, 1 / 3, 2 / 3])


def test_repair_cost_scales_with_area_and_severity():
    cost = repair_cost(np.array([100.0, 100.0]), np.array([0.0, 1.0]))
    assert list(cost) == pytest.approx([100 * SEVERITY_MIN, 100.0])


def test_section_lanes_uses_tag_or_class_default():
    D = nx.DiGraph()
    road(D, 0, 1, "A", "primary", lanes="3")
    road(D, 2, 3, "B", "primary")
    road(D, 4, 5, "C", "residential", oneway=True)
    s = {x.name: x for x in build_sections(D)}
    assert section_lanes(D, s["A"]) == 3
    assert section_lanes(D, s["B"]) == 4
    assert section_lanes(D, s["C"]) == 1


def test_section_table_columns_and_value(city):
    sections = build_sections(city)
    scores = {e: 0.0 for e in city.edges}
    scores[(1, 2)] = 1.0
    crit = section_criticality(city, sections, scores)
    sid = edge_to_section(sections)[(1, 2)]
    df = section_table(city, sections, crit, {sid: 4}, {sid: 3}).set_index("section_id")
    r = df.loc[sid]
    assert r["requests"] == 4 and r["request_points"] == 3
    assert r["condition"] == 1.0 and r["criticality"] == 1.0
    assert r["area_m2"] == pytest.approx(300 * 2 * LANE_WIDTH_M)
    assert r["value"] == pytest.approx(1.0 * 1.0 * 0.3)
    assert (df.drop(sid)["value"] == 0).all()


def test_gini():
    assert gini([1, 1, 1, 1]) == pytest.approx(0.0)
    assert gini([0, 0, 0, 4]) == pytest.approx(0.75)


# --- baseline ------------------------------------------------------------------


def brute_force(values, costs, budget):
    best = 0.0
    for r in range(len(values) + 1):
        for combo in itertools.combinations(range(len(values)), r):
            if sum(costs[i] for i in combo) <= budget:
                best = max(best, sum(values[i] for i in combo))
    return best


def test_greedy_can_miss_the_optimum_exact_does_not():
    # equal ratios: greedy takes "a" (id order) and has no room left for b + c
    ids, values, costs = ["a", "b", "c"], [10.0, 6.0, 6.0], [10.0, 6.0, 6.0]
    g = baseline.greedy(ids, values, costs, budget=12)
    e = baseline.exact(ids, values, costs, budget=12)
    assert g.chosen == ["a"] and g.total_value == 10
    assert e.chosen == ["b", "c"] and e.total_value == 12


def test_exact_matches_brute_force_and_respects_budget():
    rng = random.Random(0)
    for _ in range(20):
        n = rng.randint(1, 9)
        values = [round(rng.uniform(0, 10), 3) for _ in range(n)]
        costs = [round(rng.uniform(0.1, 10), 3) for _ in range(n)]
        budget = rng.uniform(0, sum(costs))
        ids = [f"s{i}" for i in range(n)]
        e = baseline.exact(ids, values, costs, budget)
        g = baseline.greedy(ids, values, costs, budget)
        assert e.total_value == pytest.approx(brute_force(values, costs, budget), abs=1e-6)
        assert e.total_cost <= budget + 1e-9 and g.total_cost <= budget + 1e-9
        assert g.total_value <= e.total_value + 1e-9


def test_zero_value_items_are_never_chosen():
    g = baseline.greedy(["a", "b"], [0.0, 1.0], [0.0, 1.0], budget=5)
    e = baseline.exact(["a", "b"], [0.0, 1.0], [0.0, 1.0], budget=5)
    assert g.chosen == ["b"] and e.chosen == ["b"]
