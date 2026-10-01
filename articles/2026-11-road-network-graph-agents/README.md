# Graph agents that plan road maintenance

**Status:** drafts complete, in review (EN, EN Medium, PT-BR, LinkedIn EN/PT-BR) · **Branch:** `article/2026-11-road-network-graph-agents` · **Target date:** 2026-11-27

Maintenance planning for Belo Horizonte's real road network (OpenStreetMap, 19,842 sections) and 198,991 Tapa-Buraco pothole requests (PBH open data, Aug 2022 – Jul 2023), with deterministic graph tools in NetworkX and three Pydantic AI agents on a local Qwen3-8B, compared with a greedy knapsack and a non-LLM scheduling heuristic. The solver is within 1e-5 of optimal, so the maintenance agent can only trade value (93.8–100% of the solver's) for up to +1.08 points of request coverage; the closure agent finished 1 of 9 schedules, 6 of its 8 failures from one mistyped id; and 98.8% of prose numbers trace to tools while some sentences around them are still wrong. See [PLAN.md](PLAN.md) and [code/docs/RESULTS.md](code/docs/RESULTS.md).

| | |
|---|---|
| Article (EN) | [article-en.md](article-en.md) · Medium short version: [article-en-medium.md](article-en-medium.md) |
| Article (PT-BR) | [article-pt-br.md](article-pt-br.md) |
| LinkedIn | [EN](linkedin-en.md) · [PT-BR](linkedin-pt-br.md) |
| Code | [code/](code/) |
| Plan | [PLAN.md](PLAN.md) |

## Published

- Medium: [[LINK]]
- LinkedIn: [[LINK]]
