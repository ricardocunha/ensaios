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
4. ~~Still open: a source of official alert times per municipality.~~ Partly resolved in milestone 2: SGB SACE Taquari bulletins (see below). Municipal Defesa Civil alert times are still not machine-readable.

## Milestone 2 result (2026-09-30)

Numbers: [code/docs/RESULTS.md](code/docs/RESULTS.md). Sources and verification: [code/docs/DATA.md](code/docs/DATA.md).

- **Dataset:** `data/cache/hourly.csv`, one row per station and UTC hour (7 ANA gauges, 7 INMET stations, 04-20 → 05-20 plus 72 h warm-up). Level is the last real reading in the hour; empty hours stay empty, and every row carries the time and age of the latest reading. Nothing is interpolated.
- **Clocks and units resolved:** ANA is local time UTC-3 and cm (SACE bulletins match ANA at the same clock time; the Estrela crest was marked in the field at 13:30 on 05-02 at 33.66 m, ANA says 3366 at 13:30); INMET rows are hour-ending (solar-noon test). EMS times are UTC by inference only.
- **Signals** (`signals/`): ANA level (station bands from the 2019–2024-04 record, official flood level on top, ×2 for a 1 m rise in 6 h), ANA gauge rain and INMET rain (fixed 24 h / 72 h bands), Copernicus EMS as a *label* visible only from its delivery time. Each signal has LR, freshness and reliability; a silent gauge keeps its last real value with a decaying reliability, then becomes an explicit "missing" signal after 72 h.
- **Alert times:** the SGB SACE Taquari archive lists every 2024 bulletin with data and upload times (first: data 04-30 06:00, uploaded 07:54 local). No machine-readable Defesa Civil or CEMADEN municipal alerts. Fallback "in time" reference: first ANA reading at or above the official flood level (Estrela 04-30 08:15, Encantado 04-30 14:15, Taquari 05-01 04:15, Muçum 05-01 12:45, Cais Mauá 05-02 13:15, local).
- **Harness:** `backtest.replay` gives adapters only a point-in-time snapshot; tests check signals at every step against a dataset truncated at that step, a future spike, latency, and EMS delivery vs acquisition.
- **Findings for the article:** gauges fail at the crest (Encantado has no level for 105 h from 04-30 22:00 local; Cais Mauá stops at 23:15 on 05-02, three days before the 5.37 m crest; the same happened at Muçum in September 2023, so historical maxima under-state floods). Single signals already cross LR ≥ 10 on 04-30 at Estrela and Encantado, the day the first SACE bulletin went out.
- **Next (milestone 3):** fusion in log-odds with reliability weights, mapping of rain stations to municipalities, scoring against the flood-level crossings and SACE times, and quiet-period false alarms (the 2019–2024 record is already cached).

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
