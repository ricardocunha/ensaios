# Results

Every number the drafts use comes from here. Machine: Apple M4 Pro, 48 GB,
macOS (Darwin 25.4.0), Python 3.12, OSMnx 2.1.1, NetworkX 3.7 (pure Python,
single-threaded). OSM data downloaded 2026-09-30.

## Milestone 1: city choice (2026-09-30)

### Graph size (`network_type="drive"`, simplified)

| City | Nodes | Edges (MultiDiGraph) | Edges (DiGraph, parallel collapsed) | First download + GraphML save | Load from cache |
|---|---:|---:|---:|---:|---:|
| Porto Alegre | 21,244 | 50,350 | 50,180 | 83.6 s | 1.36 s |
| Belo Horizonte | 32,311 | 82,984 | 82,718 | 119.7 s | 1.88 s |

### Edge betweenness (travel-time weighted), `scripts/bench_betweenness.py`

`k` = number of sampled source nodes (seed 42). "Top-100 overlap" = share of
the exact top-100 edges that the sampled run also puts in its top 100. Both
cities ran at the same time in two processes, so timings include some
contention.

| City | k=100 | k=500 | k=2000 | Exact | Top-100 overlap k=100 / 500 / 2000 |
|---|---:|---:|---:|---:|---|
| Porto Alegre | 8.5 s | 42.7 s | 192.9 s | 1,640.5 s (27.3 min) | 0.75 / 0.86 / 0.98 |
| Belo Horizonte | 15.9 s | 84.1 s | 321.1 s | stopped after ~1 h (not finished); extrapolated ~69–86 min | not measured |

**Belo Horizonte exact run.** The process ran 1 h 02 min 40 s in total and
was stopped by hand (the machine is shared with other long jobs). The sampled
runs before it took ~7 min, so the exact phase had run ~55 min without
finishing. No exact result and no top-100 overlap for Belo Horizonte.

**How the exact time is extrapolated.** Betweenness does one single-source
Dijkstra per source node, so time grows about linearly with the number of
sources. From the k=2000 run: 321.1 s / 2000 = 0.161 s per source, × 32,311
nodes = 5,188 s (~86 min). The same method on Porto Alegre (192.9 s / 2000 ×
21,244 = 2,049 s) overestimated its measured exact time (1,640.5 s) by 25%;
applying that factor (1,640.5 / 2,049 = 0.80) gives ~4,150 s (~69 min). So
the Belo Horizonte exact run would take roughly 69–86 min on this machine,
consistent with it not finishing in ~55 min. This is an estimate, not a
measurement.

**Recommended k.** k=500 while developing and inside agent loops (84.1 s on
Belo Horizonte; 0.86 top-100 overlap with exact on Porto Alegre) and k=2000
for the numbers the article reports (321.1 s on Belo Horizonte; 0.98 overlap
on Porto Alegre). The overlap figures were measured on Porto Alegre only; we
assume Belo Horizonte behaves similarly. [[VERIFY: top-100 overlap on Belo
Horizonte, e.g. k=2000 vs. k=8000, if a check is needed]]

Raw rows: `runs/bench_betweenness.jsonl` (git-ignored).

### All tools once, `scripts/smoke_city.py --k 500 --pairs 1000`

Accessibility: share of graph nodes whose drive to the nearest OSM
`amenity=*` (snapped to the nearest node) is within 5 / 10 / 15 min, free-flow.

| | Porto Alegre | Belo Horizonte |
|---|---:|---:|
| Hospitals (OSM `amenity=hospital`) | 52 | 94 |
| Nodes within 5 / 10 / 15 min of a hospital | 60.0% / 93.9% / 98.0% | 85.5% / 98.7% / 99.9% |
| Median / p95 time to a hospital | 232 s / 625 s | 152 s / 438 s |
| Schools (OSM `amenity=school`) | 438 | 422 |
| Nodes within 5 min of a school | 98.9% | 99.3% |
| Criticality, k=500 | 43.9 s | 68.5 s |
| Baseline for 1,000 OD pairs | 11.7 s | 13.4 s |
| 5 single-edge closures (top-5 edges) | 15.9 s | 13.6 s |

POI download times are not comparable (the first city's run was repeated from
the cache), so they are left out.

Top-5 edges by sampled betweenness and their single-edge closure impact
(1,000 OD pairs, none disconnected):

| City | Street | Trips affected | Mean / max extra time |
|---|---|---:|---|
| Porto Alegre | Avenida Teresópolis | 144 | 24.2 s / 53.7 s |
| Porto Alegre | Avenida Coronel Aparício Borges | 145 | 17.7 s / 24.3 s |
| Porto Alegre | Avenida Teresópolis | 145 | 14.2 s / 16.7 s |
| Porto Alegre | Avenida Teresópolis | 144 | 24.2 s / 53.7 s |
| Porto Alegre | Avenida Dawid Jozef Kapel | 142 | 14.3 s / 16.7 s |
| Belo Horizonte | Anel Rodoviário Celso Mello de Azevedo | 116 | 104.4 s / 179.2 s |
| Belo Horizonte | Anel Rodoviário Celso Mello de Azevedo | 112 | 42.5 s / 53.1 s |
| Belo Horizonte | Anel Rodoviário Celso Mello de Azevedo | 112 | 12.3 s / 12.9 s |
| Belo Horizonte | Anel Rodoviário Celso Mello de Azevedo | 109 | 11.2 s / 11.4 s |
| Belo Horizonte | Anel Rodoviário Celso Mello de Azevedo | 96 | 58.8 s / 78.6 s |

The top edges are consecutive pieces of the same road. The agents should
reason about *segments* (chains of edges between junctions, or whole named
stretches), not single OSM edges.

## Milestone 2: sections, pothole requests, condition, baseline (2026-09-30)

Run: `nice uv run python scripts/section_pipeline.py belo-horizonte --k 2000`
(165.1 s in total, machine shared with another heavy job, load average
above 100 at times). Every number below is in `runs/m2-belo-horizonte-k2000.json`
(git-ignored). Betweenness cached first with `scripts/cache_betweenness.py`:
k=2000 took 278.7 s and k=500 61.9 s this time (both seed 42, run with `nice`).

### Road sections (`road_agents.sections`, max length 1,000 m)

Definition in `docs/DATA.md` ("Road sections") and the module docstring:
same name/ref and same highway class, merged through nodes where no
strictly higher-class road touches and the road does not fork; unnamed links
never merged; chains over 1,000 m cut into equal pieces at edge boundaries.

| | Value |
|---|---:|
| Directed edges (DiGraph) | 82,718 (56 self-loops left out) |
| Undirected links (both directions of a street = 1) | 49,532 |
| **Sections** | **19,842** (19,056 without the 1,000 m cap) |
| Unnamed sections / one-way sections | 2,633 / 6,762 |
| Total length (one direction per link) | 4,874 km |
| Section length median / p90 / max | 163 m / 614 m / 4,063 m (one OSM edge longer than the cap) |
| Directed edges per section, mean / max | 4.2 / 46 |
| Build time | 0.55 s |

By class: 14,423 residential, 2,705 tertiary, 542 secondary, 253 primary,
154 trunk, 84 motorway, the rest links, living streets, busways etc.

### Top-10 edges vs. top-10 sections (k=2000, 1,000 OD pairs, closure = all edges of the edge/section)

Section criticality = length-weighted mean over its links of (betweenness
u→v + v→u). OD baseline 12.7 s; the 30 closures below 93.2 s.

- **Top-10 edges:** 9 on "Anel Rodoviário Celso Mello de Azevedo", 1 on
  Avenida Waldir Soeiro Emrich / Avenida Quatro Mil Cento e Setenta e Dois.
  They fall in **8 distinct sections**.
- **Top-10 sections:** all 10 are Anel Rodoviário pieces (motorway, 383–2,004 m).
  Sections remove the duplicates (two pairs of top edges were the same
  section) but do not change the story: the Anel dominates betweenness.
- **Top-10 roads** (best section per distinct name) is the useful list for
  the agents:

| # | Road (best section) | Class | Length | Trips affected | Mean / max extra time |
|---|---|---|---:|---:|---|
| 1 | Anel Rodoviário Celso Mello de Azevedo (S00112) | motorway | 1,005 m | 112 | 42.5 s / 53.1 s |
| 2 | Avenida Waldir Soeiro Emrich (S01760) | primary | 728 m | 85 | 90.9 s / 122.8 s |
| 3 | Rodovia Anel Rodoviário Celso Mello Azevedo (S02443)* | motorway | 1,240 m | 90 | 19.5 s / 26.9 s |
| 4 | Avenida Presidente Antônio Carlos (S01395) | trunk | 953 m | 75 | 60.0 s / 222.3 s |
| 5 | Rua Desembargador Reis Alves (S06302) | primary | 774 m | 88 | 43.0 s / 89.4 s |
| 6 | Rua Juarez Teixeira Pinto (S10128) | primary | 1,102 m | 63 | 75.9 s / 87.1 s |
| 7 | Avenida Cristiano Machado (S00611) | trunk | 306 m | 69 | 21.9 s / 31.0 s |
| 8 | Avenida Quatro Mil Cento e Setenta e Dois (S01500) | primary | 884 m | 111 | 388.9 s / 689.4 s |
| 9 | Avenida Dom Pedro I (S00702) | trunk | 1,357 m | 60 | 99.4 s / 440.9 s |
| 10 | Avenida 3153 (S00200) | trunk | 721 m | 100 | 45.2 s / 140.6 s |

\* The same road under a second OSM name; name matching does not merge it.
No closure in these lists disconnects more than 1 of 1,000 trips (one top
edge, S00113, disconnects 1).

Criticality ranking vs. single-edge ranking: the worst *closure* is not the
highest betweenness. Section S01500 (8th road) delays 111 trips by a mean
388.9 s; the top Anel section delays 112 trips by 42.5 s. Closure impact is a
separate signal from betweenness: the section table carries
betweenness, and closure impact is a tool call (`closure_impact`).

**k=500 vs. k=2000 on sections:** top-10 overlap 0.6, top-100 0.93,
top-1,000 0.921. Use k=2000 for reported rankings.

### Pothole requests (Tapa-Buraco), Aug 2022 – Jul 2023

Files: `dadosabertos_bhdigital_2022.csv` (Aug–Dec used) and the seven 2023
monthly files (Jan–Jul). Load + parse 3.3 s.

| | Value |
|---|---:|
| Requests in the window | 198,991 |
| With coordinates | 198,955 (36 without) |
| Distinct locations (lat/lon to 6 decimals) | 88,942 |
| Status "Serviço realizado" / "não realizado" / open | 188,596 / 9,858 / 537 |
| Channel: Integração entre Sistemas / Portal / Portal Mobile / other | 115,314 / 45,702 / 37,423 / 552 |
| Access level | all 198,991 "Restrito" |

Per month: Aug 8,264 · Sep 6,535 · Oct 14,864 · Nov 17,229 · Dec 19,773 ·
Jan 32,266 · Feb 24,870 · Mar 18,882 · Apr 18,264 · May 16,225 · Jun 10,908 ·
Jul 10,911 (a rainy-season peak in Dec–Feb).

**Snapping** to the nearest drivable link (EPSG:31983, `geopandas.sjoin_nearest`), 2.0 s:

| Threshold | 5 m | 10 m | 15 m | **30 m (used)** | 50 m | 100 m |
|---|---:|---:|---:|---:|---:|---:|
| Share of requests with coordinates within | 1.6% | 28.2% | 67.3% | **95.0%** | 98.6% | 99.7% |

Snapped at 30 m: 189,075 requests (unsnapped share **4.97%** of those with
coordinates). Distance median 12.5 m, p90 23.3 m, p95 29.9 m. The
coordinates look like geocoded addresses (few within 5 m of a centre line),
which fits the address fields in the file.

### Condition score (`road_agents.condition`)

- Sections with ≥1 request location: **12,076 of 19,842 (60.9%)**, covering
  82.2% of the network's km. 84,811 distinct locations snapped.
- Network rate: 17.4 distinct locations per km per year.
- Per section with requests: median 4 locations, p90 16, p99 36, max 84.
  Smoothed rate median 18.0/km, p90 28.3, max 66.2.
- Concentration: Gini 0.70 over all sections; the top 10% of sections hold
  48.3% of locations.
- By class (locations per km): residential 21.0, tertiary 12.5, secondary
  8.2, primary 5.4, trunk 2.6, motorway 0.10. Requests come mostly from
  residential streets; the Anel Rodoviário (motorway) has almost none.
- Spearman correlation of smoothed rate with criticality: −0.09 (all
  sections), −0.12 (sections with requests). Condition and criticality are
  nearly independent, so the product ranks differently from either.
- Top-10 by condition are all residential streets (e.g. Rua Augusto Abreu,
  311 m, 45 locations; Rua das Verbenas, 954 m, 84).
- OSM `lanes` tagged on at least one link of 25.0% of sections; the rest use
  class defaults. Total pavement area (assumed widths) 33.9 million m².

### Knapsack baseline (`road_agents.baseline`)

Candidates: 11,860 sections with value > 0 (216 sections with requests have
zero sampled betweenness). Budget = share of the candidates' total repair
cost (16.8 million cost units = m² of full resurfacing).

| Budget | Method | Sections | km | Value captured | Requests on chosen sections | Time |
|---|---|---:|---:|---:|---:|---:|
| 5% | greedy | 445 | 174.8 | 54.43% | 10,127 (5.4%) | 0.02 s |
| 5% | exact (HiGHS) | 439 | 174.8 | 54.43% | 10,068 (5.3%) | 14.3 s |
| 10% | greedy | 952 | 362.6 | 70.24% | 20,596 (10.9%) | 0.01 s |
| 10% | exact | 951 | 362.7 | 70.24% | 20,593 (10.9%) | 18.9 s |
| 20% | greedy | 1,997 | 738.9 | 83.98% | 40,940 (21.7%) | 0.01 s |
| 20% | exact | 1,994 | 738.7 | 83.98% | 40,925 (21.6%) | 15.0 s |

Greedy (value/cost ratio) is within 9e-6 (5%), 1.3e-6 (10%) and 1.5e-6
(20%) of the optimum; the chosen sets overlap with Jaccard 0.982 / 0.997 /
0.996. The top-value picks at every budget are Avenida Waldir Soeiro
Emrich, Avenida Amazonas, Avenida Vilarinho, Avenida Cristiano Machado and
Avenida Presidente Tancredo Neves. Value is concentrated (5% of the budget
captures 54% of value) because betweenness is heavy-tailed; the plan buys
arterials with some requests, not the streets with the most requests.

## Milestone 3: agents vs. the pure solver (2026-09-30)

Code: `src/road_agents/planning.py` (tools), `agents.py` (Pydantic AI 2.52
agents), `audit.py` (evaluation), `scripts/evaluate_agents.py`. Model:
Qwen3-8B 4-bit (MLX) behind the shared `mlx_lm.server` at
`localhost:8088/v1`, thinking off, temperature 0.7, top_p 0.8. Trips: the
same 1,000 sampled OD pairs as milestone 2. Access: graph nodes within 10 min
of an OSM hospital / 5 min of an OSM school (free-flow). Solver = greedy
knapsack at k=2000 values (within 1e-5 of the exact MILP, milestone 2).

**Set-up of the comparison.** The quarter has 3 months. The 15 plan sections
with the highest criticality are the *major works* (all trunk/primary/
motorway pieces of Anel, Waldir Soeiro Emrich, Antônio Carlos, Cristiano
Machado, …); each must go to one month, at most 5 per month. A *violation*
is a month whose simultaneous closures make nodes lose hospital or school
access that no single work of that month cuts alone (an interaction that
sequencing can avoid). Three schedules are scored with the same exact tool
(`schedule_report`): *naive* (priority order, criticality descending, 5 per
month), *heuristic* (deterministic: pairwise conflict check + greedy + swap
search, no LLM), and the *agent's*.

### Pure-solver arm (deterministic, from `runs/m3-eval-scripted.jsonl`)

| Budget | Sections | Value captured | Budget used | Requests covered | Naive: violations / interaction nodes / worst-month delay | Heuristic: violations / worst-month delay |
|---|---:|---:|---:|---:|---|---|
| 5% | 445 | 54.43% | 100.0% | 5.36% | 1 / 2 / 67,089.5 s | 0 / 51,731.9 s |
| 10% | 952 | 70.24% | 100.0% | 10.89% | 1 / 2 / 61,563.3 s | 0 / 50,883.2 s |
| 20% | 1,997 | 83.98% | 100.0% | 21.65% | 1 / 6 / 29,514.6 s | 0 / 21,619.8 s |

"Worst-month delay" = total extra travel time over the 1,000 sampled trips
with that month's works all closed. The naive schedule's violation comes
from the same pair at every budget: Anel Rodoviário S00102 with Avenida
Presidente Antônio Carlos S01395 in month 1 (2 interaction nodes); at 20%
also Waldir Soeiro Emrich S01749 + S01760 (6 interaction nodes in total).
Pairs from `planning.pair_conflicts` / `schedule_report`. A non-LLM heuristic
removes all violations and lowers the worst month by 17–27% (5%: 22.9%,
10%: 17.3%, 20%: 26.7%). **This is the bar for the closure agent.**

Most access loss is not an interaction. Closed alone, the major works cut
0–6 nodes each from 10-min hospital access (S01394, Antônio Carlos: 6;
S00611, Cristiano Machado: 0): nodes on or behind the closed section, which
no sequencing can fix. Per month, the schedules above lose 9–20 hospital
nodes in total (graph has 32,311 nodes). With free-flow times and 94 OSM
hospitals, 10-min coverage is 98.7% before any closure, so the access
constraint bites only locally.

Timings (machine shared with other jobs, load average 30–60): planning data
load 16.1–19.6 s (graph, sections, POIs, 1,000-pair OD baseline); solver arm
per budget 57–141 s (mostly the heuristic's closure recomputations).

### Dry run without an LLM (`--model scripted`, `runs/m3-eval-scripted.jsonl`)

A scripted `FunctionModel` (adds the most-requested section left out, S09924
with 509 requests; round-robin months by criticality; copies tool numbers)
exercises the whole pipeline on the real data: every agent returns a typed
output, the final plan is feasible (100.0% budget use; value 99.85 / 99.95 /
99.98% of the solver's at 5 / 10 / 20%), and the structured audit matches
12/12 month fields at each budget; the prose audit finds 3 of 4 numbers, the missing one being a number planted as fabricated (123.45). Round-robin by criticality still has 1
violation per budget: the conflicts are not visible from single-work numbers.
Pipeline wall time 22–39 s per run (tools only, no LLM), plus the evaluation.

### Smoke with Qwen3-8B (SMOKE, 1 pipeline at 10%, not the evaluation)

`runs/m3-smoke.jsonl`, request limits 5 / 6 / 2, then one closure-agent-only
debug run with a limit of 3. At most 15 LLM requests in total. The tool
output of `check_schedule` did not yet name the conflicting pairs (added
after this smoke).

| Agent | Result | Requests | Wall time |
|---|---|---:|---:|
| Maintenance | failed: request limit 5 reached before an output. It called `rank_sections` 4 times (requests / value-per-cost / criticality not in plan; value in plan), then `try_plan` with 15 adds and 5 removals (the instructions say at most 6) | 5 | 26.9 s |
| Closure | failed: `check_schedule` exceeded its 2 retries (the failing arguments were not logged in that version) | ≤ 6 | 40.5 s |
| Coordinator | ok (fell back to the solver plan, no schedule) | 1 (1,032 in / 285 out tokens) | 14.2 s |
| Closure, debug run | failed at the limit of 3: proposed month 1 = S00102, S01756, S01758, S01750, S01393 (Anel + three Waldir Soeiro Emrich sections + Antônio Carlos; the tool reported a VIOLATION with 3 hospital + 3 school interaction nodes), then re-checked the *same* month sets twice, only reordered | 3 | 37.1 s |

Number audit of the coordinator's prose: 11 of 12 numbers found in the tool
ledger; the one not found, "gives up on 29.76% of the total value", is
100 − 70.24, a correct derived number that the audit (verbatim lookup only)
does not credit.

What the smoke says so far (smoke, n=1): with a small request budget the 8B
model explores instead of converging, and on sequencing it did not act on a
tool output that said VIOLATION. Changes made after the smoke, before the
queued run: `check_schedule` names the conflicting pairs, the instructions
tell the agent to move one work of each pair and not to re-check a schedule,
the closure agent gets 3 retries, and failed runs keep a transcript.

### Full evaluation (queued)

`scripts/run_after_queue.sh` (nohup) waits for the compliance article's
`QUEUE_DONE`, then runs 3 × {5, 10, 20%} with limits 12 / 14 / 4 into
`runs/m3-eval-local.jsonl` (+ `.summary.json`).

- Value captured, agent vs. solver: [[RESULT: m3-eval-local value_share_pct per run vs 54.43 / 70.24 / 83.98%]]
- Budget use: [[RESULT: budget_used_pct per run]]
- Deviations proposed and their value cost: [[RESULT: adds / removes, value_vs_solver_pct]]
- Access-loss violations, agent vs. naive (1/1/1) vs. heuristic (0/0/0): [[RESULT: agent_violations per run]]
- Worst-month delay, agent vs. heuristic: [[RESULT: agent_peak_delay_s vs heuristic_peak_delay_s]]
- Closure-scenario audit, stated vs. recomputed month numbers: [[RESULT: phase_fields_ok / phase_fields; flags_ok; flags_missed]]
- Prose numbers found in the tool ledger: [[RESULT: text_numbers_grounded]]
- Consistency over 3 runs: [[RESULT: deviation_jaccard_mean, final_plan_jaccard_mean, schedule_co_assignment_mean, value_share_pct_std]]
- Agent failures and wall time per pipeline: [[RESULT: agents_ok, errors, mean_seconds_per_pipeline]]
