"""Tests on tiny synthetic graphs. No network access."""

from __future__ import annotations

import networkx as nx
import pytest

from road_agents.graph import cache_path, slugify, to_simple_digraph
from road_agents.tools import (
    accessibility,
    accessibility_loss,
    closure_impact,
    compute_baseline,
    edge_criticality,
    isochrone,
    sample_od_pairs,
    snap_points,
    time_to_nearest,
    top_edges,
)


def two_way(D: nx.DiGraph, u: int, v: int, t: float) -> None:
    D.add_edge(u, v, travel_time=t)
    D.add_edge(v, u, travel_time=t)


@pytest.fixture
def bridge_graph() -> nx.DiGraph:
    """Two triangles joined by a fast bridge (2-3) and a slow detour (0-5).

        0 - 1       4 - 5
         \\ |       | /
           2 ===== 3
    """
    D = nx.DiGraph()
    for u, v in [(0, 1), (1, 2), (0, 2), (3, 4), (4, 5), (3, 5)]:
        two_way(D, u, v, 10)
    two_way(D, 2, 3, 10)  # bridge
    two_way(D, 0, 5, 100)  # slow detour
    for n in D.nodes:
        D.nodes[n]["x"] = -51.2 + 0.01 * n
        D.nodes[n]["y"] = -30.0
    return D


def test_to_simple_digraph_keeps_fastest_parallel_edge():
    G = nx.MultiDiGraph()
    G.add_edge(1, 2, key=0, travel_time=30.0, name="slow")
    G.add_edge(1, 2, key=1, travel_time=12.0, name="fast")
    G.add_edge(2, 1, key=0, travel_time=20.0)
    D = to_simple_digraph(G)
    assert D.number_of_edges() == 2
    assert D[1][2]["travel_time"] == 12.0
    assert D[1][2]["name"] == "fast"
    assert D[1][2]["key"] == 1


def test_cache_path_is_slugged(tmp_path):
    assert slugify("Porto Alegre, RS") == "porto-alegre-rs"
    assert cache_path("porto-alegre", tmp_path) == tmp_path / "porto-alegre-drive.graphml"


def test_bridge_is_most_critical(bridge_graph):
    scores = edge_criticality(bridge_graph)
    top2 = {e for e, _ in top_edges(scores, 2)}
    assert top2 == {(2, 3), (3, 2)}


def test_sampled_criticality_is_deterministic(bridge_graph):
    a = edge_criticality(bridge_graph, k=3, seed=7)
    b = edge_criticality(bridge_graph, k=3, seed=7)
    assert a == b


def test_k_at_least_n_falls_back_to_exact(bridge_graph):
    assert edge_criticality(bridge_graph, k=100) == edge_criticality(bridge_graph)


def test_sample_od_pairs_is_deterministic_and_distinct(bridge_graph):
    pairs = sample_od_pairs(bridge_graph, 10, seed=1)
    assert pairs == sample_od_pairs(bridge_graph, 10, seed=1)
    assert len(pairs) == len(set(pairs)) == 10
    assert all(o != d for o, d in pairs)


def test_sample_od_pairs_caps_at_all_pairs(bridge_graph):
    assert len(sample_od_pairs(bridge_graph, 10_000)) == 6 * 5


def test_closure_of_bridge_forces_detour(bridge_graph):
    # 2 -> 3 is 10s over the bridge. Without it: 2-0 (10) + 0-5 (100) + 5-3 (10) = 120s.
    impact = closure_impact(bridge_graph, [(2, 3)], [(2, 3), (0, 1)])
    assert impact.n_pairs == 2
    assert impact.n_affected == 1
    assert impact.n_disconnected == 0
    trip = impact.trips[0]
    assert (trip.before_s, trip.after_s, trip.delta_s) == (10.0, 120.0, 110.0)
    assert impact.total_delay_s == impact.max_delay_s == impact.mean_delay_s == 110.0


def test_closure_matches_full_recomputation(bridge_graph):
    pairs = sample_od_pairs(bridge_graph, 30)
    closed = [(2, 3), (3, 2)]
    impact = closure_impact(bridge_graph, closed, pairs)
    H = bridge_graph.copy()
    H.remove_edges_from(closed)
    expected = 0.0
    for o, d in pairs:
        expected += nx.dijkstra_path_length(H, o, d, weight="travel_time") - nx.dijkstra_path_length(
            bridge_graph, o, d, weight="travel_time"
        )
    assert impact.total_delay_s == pytest.approx(expected)


def test_closure_can_disconnect(bridge_graph):
    closed = [(2, 3), (0, 5)]  # both ways from the left triangle to the right
    impact = closure_impact(bridge_graph, closed, [(1, 4)])
    assert impact.n_affected == impact.n_disconnected == 1
    assert impact.trips[0].after_s is None
    assert impact.to_dict()["n_disconnected"] == 1
    assert "trips" not in impact.to_dict()


def test_closure_rejects_unknown_edge(bridge_graph):
    with pytest.raises(KeyError):
        closure_impact(bridge_graph, [(1, 4)], [(0, 1)])


def test_closure_does_not_mutate_graph(bridge_graph):
    before = bridge_graph.number_of_edges()
    closure_impact(bridge_graph, [(2, 3)], [(2, 3)])
    assert bridge_graph.number_of_edges() == before


def test_snap_points_picks_nearest_node(bridge_graph):
    assert snap_points(bridge_graph, [(-51.2 + 0.041, -30.0), (-51.3, -30.0)]) == [4, 0]


def test_time_to_nearest_is_directional():
    D = nx.DiGraph()
    D.add_edge(1, 2, travel_time=5)
    D.add_edge(2, 3, travel_time=5)  # one-way street into the hospital at 3
    t = time_to_nearest(D, [3])
    assert t == {3: 0, 2: 5, 1: 10}
    assert time_to_nearest(D, [1]) == {1: 0}  # nobody can drive to node 1


def test_isochrone(bridge_graph):
    assert isochrone(bridge_graph, 2, 10) == {0, 1, 2, 3}
    assert isochrone(bridge_graph, 2, 20) == {0, 1, 2, 3, 4, 5}


def test_accessibility_shares(bridge_graph):
    # Hospital at node 4. Times: 4:0, 3:10, 5:10, 2:20, 0:30, 1:30.
    acc = accessibility(bridge_graph, [4], thresholds_s=(10, 20, 30))
    assert acc["n_reachable"] == 6
    assert acc["share_within"] == {10: 3 / 6, 20: 4 / 6, 30: 1.0}
    assert acc["median_s"] == 15.0


def test_accessibility_loss_from_bridge_closure(bridge_graph):
    # Before: 0, 1, 2 reach the hospital at 4 in 20-30s over the bridge.
    # After closing 2->3 they must take the 0-5 detour (110-120s), beyond 60s.
    loss = accessibility_loss(bridge_graph, [4], [(2, 3)], threshold_s=60)
    assert (loss["n_before"], loss["n_after"]) == (6, 3)
    assert loss["lost_nodes"] == [0, 1, 2]


def test_baseline_is_reusable_across_closures(bridge_graph):
    pairs = sample_od_pairs(bridge_graph, 30)
    base = compute_baseline(bridge_graph, pairs)
    for closed in ([(2, 3)], [(0, 5)], [(2, 3), (3, 2)]):
        assert closure_impact(bridge_graph, closed, base) == closure_impact(bridge_graph, closed, pairs)
