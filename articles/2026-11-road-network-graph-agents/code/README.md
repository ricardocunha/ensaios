# road_agents

Deterministic graph tools for the article *Graph agents that plan road
maintenance*. The agents (milestone 3) reason; these tools do the math.

```bash
make install
make test                          # synthetic graphs, no network
make smoke CITY=belo-horizonte     # downloads OSM once, caches in data/
```

## Tools (`src/road_agents/`)

| Module | Function | What it does |
|---|---|---|
| `graph.py` | `load_graph(city)` | Drivable OSM graph via OSMnx, with `travel_time`; cached as GraphML in `data/`. |
| | `to_simple_digraph(G)` | Collapses parallel edges (keeps the fastest). All tools take this `DiGraph`. |
| `pois.py` | `load_pois(city, "hospital" \| "school")` | OSM `amenity=*` features as centroids, cached as CSV. |
| `tools.py` | `edge_criticality(D, k)` | Travel-time-weighted edge betweenness; exact or sampled with `k` sources and a fixed seed. |
| | `sample_od_pairs`, `compute_baseline` | Reproducible origin–destination trips and their no-closure shortest paths. |
| | `closure_impact(D, closed, baseline)` | Exact travel-time deltas, affected and disconnected trips when edges close. Only trips that used a closed edge are recomputed. |
| | `snap_points`, `time_to_nearest`, `isochrone` | Snap POIs to nodes; time from every node to its nearest facility; reachable set within a time budget. |
| | `accessibility`, `accessibility_loss` | Share of nodes within 5/10/15 min of a facility; nodes that lose access when edges close. |

Travel times are free-flow (OSMnx imputed speeds), not congested.

## Data

See [docs/DATA.md](docs/DATA.md). Road data © OpenStreetMap contributors (ODbL):
any map or figure made from it must say so.

Measured numbers live in [docs/RESULTS.md](docs/RESULTS.md).
