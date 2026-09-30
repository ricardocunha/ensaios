# Plan: Graph agents that plan road maintenance

**Branch:** `article/2026-11-road-network-graph-agents` · **Target date:** 2026-11-27 · **Video project:** #3 (road-network graph agents)

## Question

Can LLM agents make good decisions over a road graph (which segments to fix first, what a closure does to traffic) when the graph math is done by tools and the agent does the reasoning?

## Brazilian angle

Belo Horizonte's road network from OpenStreetMap via OSMnx (chosen in milestone 1, see below). Condition data is synthetic, with a realism check against the city's open, geolocated "Tapa-Buraco" service requests (see `code/docs/DATA.md`).

## Architecture

1. **Graph tools** (NetworkX, deterministic): betweenness / edge criticality, shortest-path deltas when an edge is removed, isochrones to hospitals and schools.
2. **Maintenance agent:** ranks segments by condition × criticality × cost within a budget.
3. **Closure-impact agent:** simulates closures (road works, floods) and reports affected trips and detours.
4. **Planning coordinator:** combines both into a quarterly plan with trade-offs spelled out.

## Evaluation

- Compare the agent's plan with a pure optimization baseline (knapsack on the same scores): does the LLM add anything, or only explanation?
- Closure impact vs. ground truth from full recomputation.
- Consistency: same inputs, repeated runs.

## Milestones

1. OSMnx graph + tools + tests.
2. Synthetic condition data.
3. Agents + baseline comparison.
4. Drafts, with maps.

## Milestone 1 result (2026-09-30)

**City: Belo Horizonte.** Numbers from `code/docs/RESULTS.md` (M4 Pro, NetworkX 3.7, travel-time-weighted edge betweenness):

| | Porto Alegre | Belo Horizonte |
|---|---:|---:|
| Drive graph (nodes / edges) | 21,244 / 50,350 | 32,311 / 82,984 |
| Betweenness k=500 / k=2000 | 42.7 s / 192.9 s | 84.1 s / 321.1 s |
| Exact betweenness | 1,640.5 s (27.3 min) | stopped after ~1 h; est. 69–86 min |
| Top-100 overlap with exact, k=500 / 2000 | 0.86 / 0.98 | not measured |

Why Belo Horizonte:
- **Real pothole data.** PBH publishes BH Digital service requests (CC-BY, monthly CSVs, no account). May 2023 alone has 16,225 "Tapa-Buraco" requests, all with coordinates. Porto Alegre publishes no 156POA requests; its ombudsman file has no location. That gives milestone 2 a real-world check for the synthetic condition scores.
- **Compute is fine with sampling.** Exact betweenness is out of reach for a "few minutes" budget in either city, so both need sampled k anyway. BH at k=500 runs in under 1.5 min, k=2000 in ~5.4 min. Recommended: k=500 during development and inside agent loops, k=2000 for reported numbers.
- A clear critical corridor (Anel Rodoviário): closing its top edge adds a mean 104 s to 116 of 1,000 sampled trips.

Cost of the choice: Porto Alegre would have given the flood cross-link (May 2024 floods) for free. Belo Horizonte also floods (e.g. along the Arrudas), but that needs its own flood extents.

**What the tools do** (`code/src/road_agents/`, 18 pytest tests on synthetic graphs, no network):
- `load_graph` / `to_simple_digraph`: OSMnx drive graph with free-flow `travel_time`, GraphML cache in `data/` (git-ignored).
- `edge_criticality`: edge betweenness, exact or sampled k with a fixed seed.
- `sample_od_pairs`, `compute_baseline`, `closure_impact`: exact travel-time deltas, affected and disconnected trips for any set of closed edges; the baseline is computed once and reused, and only trips through a closed edge are rerouted (5 closures × 1,000 OD pairs in ~14 s on BH).
- `load_pois`, `snap_points`, `time_to_nearest`, `isochrone`, `accessibility`, `accessibility_loss`: OSM hospitals (94 in BH) and schools (422), time to nearest facility, share of nodes within 5/10/15 min, and nodes that lose access when edges close.

## Open questions

- **Edges vs. segments.** The top-5 edges in both cities are consecutive pieces of the same road. Agents should act on segments (edge chains between junctions, or named stretches); milestone 2 needs a segment definition.
- **Floods.** Reuse flood extents from the disaster article (Porto Alegre) or find flood-prone areas for Belo Horizonte? [[VERIFY: open flood-risk layer for BH]]
- **Pothole data.** Newer months than Jul 2023, the meaning of the "Integração entre Sistemas" channel and of `Nivel Acesso = Restrito`, and the exact CC-BY version (all marked [[VERIFY]] in `code/docs/DATA.md`). Requests measure reporting, not pavement state.
- **Hospitals.** OSM `amenity=hospital` includes private hospitals and misses UPAs/clinics; decide whether to add `amenity=clinic` / `healthcare=*` or an official list (CNES).
- **Travel times** are free-flow (OSMnx imputed speeds), so closure delays are lower bounds on real congestion effects.
- Top-100 overlap for sampled k was measured on Porto Alegre only.

## Common rules (all five articles)

- **Source:** the idea comes from the video *"5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System"* (YouTube, 2026-09-28). Credit it in the article. The architecture here is ours; don't copy the video's code or diagrams.
- **Angle:** each article is a field report with runnable code, in the style of `2026-10-cnh-ocr-smithtune`: build it, measure it, show what broke.
- **Budget:** local first (M4 Pro 48 GB, mlx / Ollama). The cap for paid APIs is **US$10 per article**, set with `--max-cost` in the code; ask before any paid run.
- **Data:** public or synthetic only. No personal data. Record every dataset's license in `code/docs/DATA.md` before using it.
- **Numbers:** every number in the drafts comes from `code/docs/RESULTS.md`. Mark gaps with `[[RESULT: …]]` / `[[VERIFY: …]]`.
- **Deliverables:** EN long version + Medium short version, PT-BR, LinkedIn EN / PT-BR, code with tests + Makefile, `CONTEXT.md` glossary, ADRs for the hard decisions.
