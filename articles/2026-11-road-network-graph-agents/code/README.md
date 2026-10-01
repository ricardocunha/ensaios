# road_agents

Deterministic graph tools for the article *Graph agents that plan road
maintenance*. The agents (milestone 3) reason; these tools do the math.

```bash
make install
make test                          # synthetic graphs, no network
make smoke CITY=belo-horizonte     # downloads OSM once, caches in data/
make betweenness                   # sampled betweenness k=500 and k=2000, cached CSV
make sections                      # milestone 2: sections, potholes, condition, baseline
make maps                          # PNG maps into ../figures
make agents-dry                    # milestone 3 pipeline with a scripted model (no LLM)
make agents-smoke                  # one pipeline with Qwen3-8B on the local mlx-lm server
make agents-eval                   # 3 runs x 5/10/20% budgets (see scripts/run_after_queue.sh)
make agents-regrade                # re-score the prose audit of runs/m3-eval-local.jsonl (no LLM)
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
| `sections.py` | `build_sections(D, max_length_m)` | Merge edges into road sections (same name and class, broken by higher-class roads, forks and a length cap). |
| | `section_criticality` | Betweenness per section (both directions summed; max and length-weighted mean). |
| `potholes.py` | `download`, `read_requests`, `load_requests` | BH Digital "Tapa-Buraco" CSVs (both file formats), cached in `data/pbh/`. |
| | `links_frame`, `snap_requests` | Snap requests to the nearest link within a distance (in memory only). |
| `condition.py` | `section_table` | Tidy per-section table: length, lanes, area, criticality, request counts, condition, synthetic repair cost, value. |
| `baseline.py` | `greedy`, `exact` | Knapsack maintenance plan within a budget (value/cost greedy; exact MILP via SciPy/HiGHS). |

## Agents (milestone 3)

| Module | What |
|---|---|
| `planning.py` | Typed deterministic tools on sections: `rank_sections`, `section_details`, `solve_budget` (knapsack with forced adds/removals), `closure_report` (trips + hospital/school access lost), `accessibility_loss_sections`, `schedule_report`, `naive_schedule`, `heuristic_schedule`, text summaries. |
| `agents.py` | Pydantic AI agents with typed outputs: maintenance-priority (deviations from the solver, each with a reason), closure-impact (month sequencing + access flags), coordinator (quarterly plan, trade-offs). `run_pipeline` chains them. |
| `audit.py` | Deterministic evaluation: plan vs. solver, schedule violations, a recomputation of every structured number and a ledger lookup of every number in the prose (strict, plus a lenient re-score that classifies misses as notation / derived / upstream / unsupported), consistency across runs. |
| `scripted.py` | A scripted `FunctionModel` stand-in for tests and dry runs. |

Model: Qwen3-8B (4-bit MLX) behind `mlx_lm.server`, OpenAI-compatible, thinking
off. Override with `ROAD_AGENTS_BASE_URL` / `ROAD_AGENTS_MODEL`.

Travel times are free-flow (OSMnx imputed speeds), not congested.

## Data

See [docs/DATA.md](docs/DATA.md). Road data © OpenStreetMap contributors (ODbL):
any map or figure made from it must say so.

Measured numbers live in [docs/RESULTS.md](docs/RESULTS.md).
