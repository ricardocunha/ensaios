# Plan: Graph agents that plan road maintenance

**Branch:** `article/2026-11-road-network-graph-agents` · **Target date:** 2026-11-27 · **Video project:** #3 (road-network graph agents)

## Question

Can LLM agents make good decisions over a road graph (which segments to fix first, what a closure does to traffic) when the graph math is done by tools and the agent does the reasoning?

## Brazilian angle

Belo Horizonte's road network from OpenStreetMap via OSMnx (chosen in milestone 1, see below). Road condition comes from the city's open, geolocated "Tapa-Buraco" pothole-repair requests, aggregated to road sections; repair costs are synthetic (milestone 2, see `code/docs/DATA.md`).

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
2. Road sections + condition data (real requests, synthetic cost) + knapsack baseline.
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

## Milestone 2 result (2026-09-30)

Numbers from `code/docs/RESULTS.md` ("Milestone 2"); definitions in `code/docs/DATA.md` ("Derived tables").

**Sections.** Consecutive edges with the same name/ref and highway class merge until a strictly higher-class road crosses or the road forks; unnamed edges stay alone; chains over 1 km are cut into equal pieces. Belo Horizonte: **19,842 sections** (19,056 without the 1 km cap) from 82,718 directed edges; median 163 m, p90 614 m. The top-10 edges fall in 8 sections, but the top-10 *sections* are still all Anel Rodoviário pieces, so the useful agent view is the top-10 *roads* (best section per name): Anel, Av. Waldir Soeiro Emrich, Av. Presidente Antônio Carlos, R. Desembargador Reis Alves, R. Juarez Teixeira Pinto, Av. Cristiano Machado, Av. Dom Pedro I, … Closing a whole section can hurt far more than its betweenness suggests (S01500 on Av. Quatro Mil Cento e Setenta e Dois: 111 of 1,000 trips, mean +389 s).

**Condition data.** 198,991 Tapa-Buraco requests, Aug 2022 – Jul 2023 (the newest month published), 88,942 distinct locations. 95.0% snap to a drivable link within 30 m (unsnapped 4.97%; median distance 12.5 m). 60.9% of sections (82.2% of km) have at least one request. Requests are a reporting signal: 21.0 locations/km on residential sections, 0.10 on the motorway (Anel); condition and criticality are nearly uncorrelated (Spearman −0.09).

**Score and cost.** `condition` = percentile of a smoothed density (distinct locations per km, 0.5 km prior at the network rate), 0 without requests. `repair_cost` = pavement area (OSM lanes or class default × 3.5 m) × (0.3 + 0.7 × condition), in m²-of-resurfacing units, no currency. `value` = condition × criticality × km. Tidy table: `code/data/belo-horizonte-sections.csv` (git-ignored).

**Baseline to beat.** 0/1 knapsack over 11,860 candidate sections. Greedy by value/cost is within 1e-5 of the exact optimum (SciPy/HiGHS, 14–19 s) at 5/10/20% budgets; 5% of the budget captures 54.4% of total value (445 sections, 175 km), 20% captures 84.0%. The plan buys arterials with some requests (Waldir Soeiro Emrich, Amazonas, Vilarinho, Cristiano Machado, Tancredo Neves), not the residential streets with the most requests: at 5% it covers only 5.4% of requests. That gap is where an agent's judgment could matter (or not) in milestone 3.

**Verify items.** Newer months: none after Jul 2023 (resolved). `Restrito`: the ticket's access class inside BH Digital per the data dictionary (resolved). "Integração entre Sistemas": 97.7% Tapa-Buraco, pothole requests almost never arrive by phone, so probably an import from another system, still unconfirmed. CC-BY version: the portal states none. Maps: `figures/bh-critical-sections.png`, `figures/bh-pothole-density.png` (section aggregates only, OSM attribution on the figure).

## Open questions

- **Edges vs. segments.** Resolved in milestone 2 (sections). Open: dual carriageways are two sections, and OSM name variants of one road are not merged.
- **Condition vs. reporting.** Requests are a proxy; residential streets dominate. Should the agent see the bias explicitly (e.g. class-normalized condition)? Who maintains the Anel pavement? [[VERIFY]]
- **Floods.** Reuse flood extents from the disaster article (Porto Alegre) or find flood-prone areas for Belo Horizonte? [[VERIFY: open flood-risk layer for BH]]
- **Pothole data.** Still open: the meaning of "Integração entre Sistemas" and the CC-BY version (both [[VERIFY]] in `code/docs/DATA.md`).
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
