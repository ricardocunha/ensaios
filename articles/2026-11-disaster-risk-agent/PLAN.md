# Plan: A disaster-risk agent that fuses signals it can't fully trust

**Branch:** `article/2026-11-disaster-risk-agent` · **Target date:** 2026-11-13 · **Video project:** #1 (multi-signal disaster intelligence)

## Question

When rain gauges, river levels, satellite imagery and history disagree, how should an agent combine them into a flood-risk alert it can explain, and would it have warned in time in a real event?

## Brazilian angle

Flooding instead of earthquakes: **Rio Grande do Sul, April–May 2024**, replayed as a backtest. [[VERIFY: data availability and licenses — CEMADEN rain gauges, ANA river levels (Hidroweb), INMET weather, Sentinel-1/2 flood extent via Copernicus, historical S2iD disaster records]]

## Architecture

1. **Signal agents** (one per source), each emitting `Signal{source, value, likelihood_ratio, freshness, reliability}`:
   rainfall, river level, satellite flood extent, and a historical RAG agent (past events for the same municipality).
2. **Bayesian fusion** in plain code (log-odds with per-source reliability), not in the LLM. The LLM explains; it doesn't do the math.
3. **Alert agent:** risk level + explanation that cites which signals moved the estimate, and how much.
4. Missing or stale sources lower confidence explicitly, instead of silently.

## Evaluation

- **Backtest:** replay the 2024 event hour by hour; compare alert times per municipality with official alerts / recorded impacts.
- Ablation: fusion with each source removed; LLM-only fusion vs. Bayesian fusion.
- Calibration (Brier score / reliability plot) across municipalities and dates, including quiet periods for false alarms.

## Milestones

1. Data audit: what's downloadable, at what resolution, for 2024. **This decides the scope.**
2. Signal adapters + cached dataset.
3. Fusion + backtest harness.
4. Agents + explanations.
5. Drafts.

## Open questions

- Satellite: precomputed flood masks vs. computing them (keep it precomputed if one exists).
- Scope: one river basin (Guaíba / Taquari) rather than the whole state.

## Common rules (all five articles)

- **Source:** the idea comes from the video *"5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System"* (YouTube, 2026-09-28). Credit it in the article. The architecture here is ours; don't copy the video's code or diagrams.
- **Angle:** each article is a field report with runnable code, in the style of `2026-10-cnh-ocr-smithtune`: build it, measure it, show what broke.
- **Budget:** local first (M4 Pro 48 GB, mlx / Ollama). The cap for paid APIs is **US$10 per article**, set with `--max-cost` in the code; ask before any paid run.
- **Data:** public or synthetic only. No personal data. Record every dataset's license in `code/docs/DATA.md` before using it.
- **Numbers:** every number in the drafts comes from `code/docs/RESULTS.md`. Mark gaps with `[[RESULT: …]]` / `[[VERIFY: …]]`.
- **Deliverables:** EN long version + Medium short version, PT-BR, LinkedIn EN / PT-BR, code with tests + Makefile, `CONTEXT.md` glossary, ADRs for the hard decisions.
