# Plan: Graph agents that plan road maintenance

**Branch:** `article/2026-11-road-network-graph-agents` · **Target date:** 2026-11-27 · **Video project:** #3 (road-network graph agents)

## Question

Can LLM agents make good decisions over a road graph (which segments to fix first, what a closure does to traffic) when the graph math is done by tools and the agent does the reasoning?

## Brazilian angle

A real Brazilian city's road network from OpenStreetMap via OSMnx (e.g. Porto Alegre or Belo Horizonte). Condition data is synthetic, with an optional look at public pothole / service-request data. [[VERIFY: open city datasets for road condition or 156 service requests]]

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

## Open questions

- Which city (size vs. compute time for betweenness).
- Whether to reuse flood extents from the disaster article for closures (a nice cross-link).

## Common rules (all five articles)

- **Source:** the idea comes from the video *"5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System"* (YouTube, 2026-09-28). Credit it in the article. The architecture here is ours; don't copy the video's code or diagrams.
- **Angle:** each article is a field report with runnable code, in the style of `2026-10-cnh-ocr-smithtune`: build it, measure it, show what broke.
- **Budget:** local first (M4 Pro 48 GB, mlx / Ollama). The cap for paid APIs is **US$10 per article**, set with `--max-cost` in the code; ask before any paid run.
- **Data:** public or synthetic only. No personal data. Record every dataset's license in `code/docs/DATA.md` before using it.
- **Numbers:** every number in the drafts comes from `code/docs/RESULTS.md`. Mark gaps with `[[RESULT: …]]` / `[[VERIFY: …]]`.
- **Deliverables:** EN long version + Medium short version, PT-BR, LinkedIn EN / PT-BR, code with tests + Makefile, `CONTEXT.md` glossary, ADRs for the hard decisions.
