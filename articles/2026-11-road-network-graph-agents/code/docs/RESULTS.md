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
