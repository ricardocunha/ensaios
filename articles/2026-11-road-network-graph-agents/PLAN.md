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

## Milestone 3 result (2026-09-30, full run 2026-09-30, analysed 2026-10-01)

Numbers from `code/docs/RESULTS.md` ("Milestone 3", "Full evaluation with Qwen3-8B").

**Tools** (`code/src/road_agents/planning.py`, typed Pydantic outputs, no LLM): `rank_sections`, `section_details`, `solve_budget` (the greedy knapsack with forced adds / exclusions), `closure_report` (trips affected and delayed over the 1,000 OD pairs + nodes losing 10-min hospital / 5-min school access, cut-off nodes separated), `accessibility_loss_sections`, `schedule_report` (per month; "interaction" access loss = lost only because works overlap, with the conflicting pairs named), `naive_schedule`, `heuristic_schedule`, and map-free text summaries.

**Agents** (`agents.py`, Pydantic AI 2.52, Qwen3-8B on the shared local mlx-lm server, thinking off):
- *Maintenance-priority*: reads the solver plan, may add/remove sections, each deviation with a reason; the final plan is rebuilt by the solver with those forced in/out, so budget feasibility is never the LLM's job. Output validator rejects unknown ids, adding what is already planned, infeasible forced sets.
- *Closure-impact*: the plan's 15 highest-criticality sections ("major works") into 3 months, at most 5 per month; tools `check_schedule`, `closure_impact`, `accessibility_loss`; must copy each month's numbers from the tools and flag access losses.
- *Coordinator*: gets a tool-computed fact sheet and writes the quarterly plan with trade-offs. Hand-off is programmatic, not agent-calls-agent.

**Evaluation** (`audit.py`, `scripts/evaluate_agents.py`): value captured, budget use, requests covered vs. the solver; schedule violations and worst-month delay vs. a naive priority-order schedule and a deterministic heuristic; a from-scratch recomputation of every structured number the closure agent states; a ledger lookup of every number in the prose (the agents' own text never enters the ledger); consistency over 3 runs (Jaccard of deviations and plans, month co-assignment agreement).

**What we already know without the LLM.** Naive sequencing of the solver's major works has 1 access violation at every budget (Anel S00102 + Antônio Carlos S01395 in the same month; at 20% also Waldir S01749 + S01760). A deterministic heuristic (pairwise conflicts + greedy + swaps) gets 0 violations and a 17–27% lower worst month. So the closure agent has a non-LLM bar to beat, and the knapsack is near-optimal on its own objective: any deviation by the maintenance agent costs value by construction (the scripted dry run's one add of the most-requested street, S09924 with 509 requests, costs 0.02–0.15% of the solver's value). The honest question for the article is whether the LLM's deviations and explanations are worth anything beyond that, and whether its numbers are right.

**Smoke (1 pipeline at 10%, ≤15 LLM requests, not the evaluation).** Maintenance agent hit its 5-request limit while exploring (4 rankings, then a what-if with 15 adds, above the stated maximum of 6). Closure agent failed twice: once on tool retries, once at a 3-request limit after re-checking the same violating month grouping (it did not act on "VIOLATION"). The coordinator produced a plan; 11 of 12 prose numbers were found in the tool ledger, the other one a correct derived number (100 − 70.24). After the smoke: `check_schedule` names the conflicting pairs, instructions say to move one of each pair and not to re-check, closure retries 2 → 3, transcripts saved for failed runs.

**Full run** (`code/runs/m3-eval-local.jsonl`, 3 runs × 5/10/20%, limits 12/14/4, 2026-09-30 21:28–22:05). Agents completed: maintenance 8/9, closure **1/9**, coordinator 9/9.

| Budget | Value vs. solver (3 runs) | Requests covered, agent (solver) | Closure ok | Worst-month delay: agent / naive / heuristic | Prose numbers grounded: strict → with notation + derived |
|---|---|---|---:|---|---|
| 5% | 95.44 / 99.74 / 93.78% | 6.11 / 5.33 / 6.40% (5.36%) | 1/3 | 66,627.6 s / 58,766.9 s / 51,731.9 s (run 1, same works; 0 / 1 / 0 violations) | 33/39, 25/30, 29/31 → 38/39, 30/30, 31/31 |
| 10% | 97.42 / 100.00* / 99.41% | 10.99 / 10.89* / 11.97% (10.89%) | 0/3 | — (naive 1 violation, heuristic 0) | 36/38, 9/9, 19/28 → 36/38, 9/9, 28/28 |
| 20% | 99.98 / 99.99 / 99.98% | 21.62 / 21.61 / 21.62% (21.65%) | 0/3 | — (naive 1 violation, heuristic 0) | 21/21, 23/25, 32/32 → 21/21, 25/25, 32/32 |

\* maintenance agent failed, solver plan stands.

- **Maintenance:** 93.8–100% of the solver's value, request coverage −0.04 to +1.08 points (best: +1.08 for 0.59% of value, 10% run 2). Deviations are not stable: mean pairwise Jaccard 0.137 (5%), 0.000 (10%), 0.867 (20%); no deviation appears in all 3 runs at 5% or 10%. 4 of 8 proposals ignore "at most 6 deviations" (10–12); the one failure is two over-long outputs in a row.
- **Closure failure (a finding, not tuned):** 6 of 8 failures are one malformed id, `S010128` for S10128 (the only work id not starting with `S0`), resent unchanged until the 3 tool retries ran out in 4 of them. 2 of 8 are loops to the request limit of 14: VIOLATION returned on all 14 calls, the flagged pair kept together (or moved into a new conflict), schedules with duplicated/missing works, the same schedule sent 8 times. Only `check_schedule` was ever called. The one success had 0 violations and correct numbers (12/12 fields, 6/6 flags), but its worst month is 28.8% above the heuristic's.
- **Grounding:** 26 of 253 prose numbers missed by the strict audit: 20 correct values in scientific notation (an audit bug: mantissa decimals), 3 correct complements in the coordinator (100 − x), 0 copied from earlier agents' text, 3 unsupported, all in maintenance claims about its own effect ("2.1% of all snapped requests", true 0.11%; "+3.77 points, from 66.01% to 69.78%", where `try_plan` showed a 4.2-point loss). Strict 227/253 (89.7%) → with notation + derived 250/253 (98.8%); coordinator 105/108 → 108/108. The lookup also credits wrong statements (requests "gave up 1.08%" when it gained 1.08 points; chance matches like "5.36% of all requests" for one street).
- **Consistency:** final plans stay close (Jaccard 0.951 / 0.955 / 0.997) because the solver refills the budget; schedule consistency not measurable (one schedule).

**Verdict.** On this problem the LLM adds explanation and small request-coverage shifts, not better plans. The knapsack is near-optimal on the stated objective, so every deviation costs value, and a coverage preference could go into the objective directly (not tested). Scheduling is better done by the deterministic heuristic: 9/9 completed, 0 violations, a lower worst month than the agent's one schedule. The 8B agents' failures are mechanical (an id, repeated calls) and their prose is traceable to tool numbers but not always right about what the numbers mean.

## Open questions

- **Edges vs. segments.** Resolved in milestone 2 (sections). Open: dual carriageways are two sections, and OSM name variants of one road are not merged.
- **Condition vs. reporting.** Requests are a proxy; residential streets dominate. Should the agent see the bias explicitly (e.g. class-normalized condition)? Who maintains the Anel pavement: resolved in `code/docs/DATA.md` (DNIT during our data window; 22.4 km municipalized on 2025-06-03, 4.1 km still DNIT).
- **Floods.** Reuse flood extents from the disaster article (Porto Alegre) or find flood-prone areas for Belo Horizonte? Not done for this article (no open flood-risk layer for BH checked).
- **Pothole data.** Still open, re-checked 2026-10-01: the meaning of "Integração entre Sistemas" and the CC-BY version. No published source answers either (the portal uses CKAN's unversioned `cc-by`); both stay as VERIFY notes in `code/docs/DATA.md` for a Fala BH / LAI request. The article does not depend on either.
- **Hospitals.** OSM `amenity=hospital` includes private hospitals and misses UPAs/clinics; decide whether to add `amenity=clinic` / `healthcare=*` or an official list (CNES).
- **Travel times** are free-flow (OSMnx imputed speeds), so closure delays are lower bounds on real congestion effects.
- **Major works only.** Milestone 3 sequences the 15 highest-criticality works; the other ~430–1,980 plan sections are assumed to run under partial closure or off-peak. Worth saying in the article.
- **Audit limits.** The strict prose audit is a verbatim lookup (rounding and %, min, km conversions only). Milestone 3 added a lenient re-score (scientific notation at real precision, 100 − x, a ± b within one text field) and keeps both. Neither can tell a number in the wrong place or with the wrong sign ("gave up 1.08%" for a gain); the structured month audit is the strict one, and the article should say so.
- Top-100 overlap for sampled k was measured on Porto Alegre only.

## Common rules (all five articles)

- **Source:** the idea comes from the video *"5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System"* (YouTube, 2026-09-28). Credit it in the article. The architecture here is ours; don't copy the video's code or diagrams.
- **Angle:** each article is a field report with runnable code, in the style of `2026-10-cnh-ocr-smithtune`: build it, measure it, show what broke.
- **Budget:** local first (M4 Pro 48 GB, mlx / Ollama). The cap for paid APIs is **US$10 per article**, set with `--max-cost` in the code; ask before any paid run.
- **Data:** public or synthetic only. No personal data. Record every dataset's license in `code/docs/DATA.md` before using it.
- **Numbers:** every number in the drafts comes from `code/docs/RESULTS.md`. Mark gaps with RESULT / VERIFY placeholders in double square brackets.
- **Deliverables:** EN long version + Medium short version, LinkedIn post, code with tests + Makefile, `CONTEXT.md` glossary, ADRs for the hard decisions.
