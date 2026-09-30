# Plan: A disaster-risk agent that fuses signals it can't fully trust

**Branch:** `article/2026-11-disaster-risk-agent` · **Target date:** 2026-11-13 · **Video project:** #1 (multi-signal disaster intelligence)

## Question

When rain gauges, river levels, satellite imagery and history disagree, how should an agent combine them into a flood-risk alert it can explain, and would it have warned in time in a real event?

## Brazilian angle

Flooding instead of earthquakes: **Rio Grande do Sul, April–May 2024**, replayed as a backtest. Data availability and licenses: audited on 2026-09-30, see "Data audit result" below.

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

## Data audit result (2026-09-30)

Details, endpoints and samples: [code/docs/DATA.md](code/docs/DATA.md).

- **Works without a key:** ANA telemetry (15-min level, flow and rain; legacy `ServiceANA.asmx`), INMET hourly stations (2024 bulk zip), Copernicus EMS **EMSR720** precomputed flood polygons (5 AOIs, all in the Taquari valley), UFRGS municipal flood-impact table for the Guaíba region (Zenodo, CC-BY-4.0).
- **Blocked:** CEMADEN history (CAPTCHA per monthly download; API needs a token) and S2iD history (open CC-BY CSV, but the server rejects scripted downloads). Both can be added by a manual browser download; the code says where to save them.
- **Needs an account (skipped):** ANA HidroWebService, INMET API, Copernicus Data Space downloads for raw Sentinel scenes.

**Feasible scope:** the **Taquari valley** (Muçum → Encantado → Roca Sales → Estrela/Lajeado → Taquari) as the main backtest, with the Guaíba at Porto Alegre as a secondary, downstream case. Signals: rainfall (INMET + ANA gauge rain), river level (ANA), satellite (EMSR720), history (S2iD, once downloaded by hand). Ground truth for "who flooded": UFRGS table (2024-05-06) + EMSR720 extents.

**What changed:**
1. Satellite is precomputed (EMSR720), not computed. No Sentinel-1 scene over the Taquari before 05-08 and Sentinel-2 was clouded on 05-01, so the satellite signal arrives on 05-04/05, after the Taquari peak (05-02). It can confirm, not warn; the article should say so.
2. CEMADEN is optional, not core: rainfall comes from INMET and ANA gauges.
3. Missing data is part of the story: key gauges (Cais Mauá, Estrela, Encantado) go quiet or sparse right at the peak. Fusion must treat "no reading" as information with its own cost.
4. Still open: a source of official alert times per municipality for the "would it have warned in time" comparison. [[VERIFY: official alert timeline source]]

## Open questions

- ~~Satellite: precomputed flood masks vs. computing them~~ Precomputed: EMSR720 exists (see audit).
- ~~Scope: one river basin (Guaíba / Taquari) rather than the whole state.~~ Taquari valley, Guaíba secondary (see audit).

## Common rules (all five articles)

- **Source:** the idea comes from the video *"5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System"* (YouTube, 2026-09-28). Credit it in the article. The architecture here is ours; don't copy the video's code or diagrams.
- **Angle:** each article is a field report with runnable code, in the style of `2026-10-cnh-ocr-smithtune`: build it, measure it, show what broke.
- **Budget:** local first (M4 Pro 48 GB, mlx / Ollama). The cap for paid APIs is **US$10 per article**, set with `--max-cost` in the code; ask before any paid run.
- **Data:** public or synthetic only. No personal data. Record every dataset's license in `code/docs/DATA.md` before using it.
- **Numbers:** every number in the drafts comes from `code/docs/RESULTS.md`. Mark gaps with `[[RESULT: …]]` / `[[VERIFY: …]]`.
- **Deliverables:** EN long version + Medium short version, PT-BR, LinkedIn EN / PT-BR, code with tests + Makefile, `CONTEXT.md` glossary, ADRs for the hard decisions.
