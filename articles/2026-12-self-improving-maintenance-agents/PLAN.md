# Plan: Maintenance agents that learn from their own mistakes

**Branch:** `article/2026-12-self-improving-maintenance-agents` · **Target date:** 2026-12-11 · **Video project:** #5 (self-improving wind turbine maintenance)

## Question

Does a maintenance agent actually get better when it keeps an episodic memory of past diagnoses and their outcomes, or does memory mostly add noise? And how would you prove it?

## Brazilian angle

Wind energy is a large part of the Northeast's grid. The data is a public wind-turbine SCADA dataset with recorded faults: CARE to Compare Wind Farm A (the EDP wind farm in Portugal) plus EDP's failure logbooks, both CC BY-SA 4.0. See `code/docs/DATA.md`.

## Architecture

1. **Detection:** Isolation Forest (plus a simple threshold baseline) on SCADA features per turbine.
2. **Diagnosis agent:** reads the anomaly window and proposes fault type and action.
3. **Episodic memory:** stores `(situation, diagnosis, outcome)`; retrieval of similar past episodes before diagnosing.
4. **Learning signals:** when the labeled outcome arrives, evaluation writes a lesson into memory. **Context gating** decides which memories are allowed into the prompt (similarity, recency, and outcome quality).
5. Optional, reusing the CNH stack: distill the corrected diagnoses into a small local model (smithtune / mlx-lm), as "continual learning" in the weights.

## Evaluation

- Chronological replay: the agent sees events in time order; score diagnosis accuracy per month.
- Arms: no memory · memory without gating · memory with gating. The claim stands only if the learning curve separates.
- Cost and latency per event.

## Milestones

1. Dataset choice + fault labels audit.
2. Detector + baseline.
3. Agent + memory + replay harness.
4. Ablation runs.
5. Drafts.

## Milestone 1 result (2026-09-30)

- **Dataset.** CARE to Compare Wind Farm A (Zenodo 15846963, CC BY-SA 4.0), downloaded on its own (158 MB) via HTTP range reads, joined with the EDP failure logbooks 2016 + 2017 (CC BY-SA 4.0, direct `.xlsx` links, no sign-up).
  - Rejected: Kelmarsh, Penmanshiel and Hill of Towie have only alarm/status logs, no failure logbook. EDP's own SCADA links return 403. CARE Farms B/C are anonymised, and C is 4.95 GB compressed.
- **Calendar fix.** Farm A timestamps are EDP's shifted by +2191 days (files 40 and 71: +2192). Undoing the shift makes all 38 overlapping file pairs agree 100 %. It also maps CARE assets to EDP turbines (0 → T07, 10 → T09, 11 → T01, 13 → T11, 21 → T06).
  - Result: 5 turbines, 2016-01 to 2017-11 (23 months), 10-minute data.
- **Labels.** 28 logbook failures (hydraulic_group 8, generator 7, generator_bearing 6, gearbox 4, transformer 3). 27 are covered by the series. Only 11 have a CARE event; CARE's 12 anomaly events include a duplicate.
  - The remarks mix real failures with sensor/alarm issues, and several rows are one incident.
- **Leakage found.** Farm A `status_type_id` is built from the logbook: code 4 = the 14 days before a fault, code 3 = the 3 days after. It is used only to clean training data, never as a feature or filter.
- **Baseline** (Isolation Forest, per turbine, `code/docs/RESULTS.md`).
  - Trained on 60 days: alarms on 13-43 % of days, driven by season. 21/24 faults have an alarm in the prior 14 days, but so do 66 % of quiet windows.
  - Trained on 365 days: quiet (0-2.4 % alarm days). Catches 3/11 of the 2017 faults at 14 days, vs a 5.3 % quiet-window rate. The hits are mostly thermal faults; only 1 of 6 hydraulic faults was caught.
- **Implications.**
  - Milestone 2 needs weather/load-normalised features.
  - The replay needs expanding-window training so the 2016 faults count.
  - Scoring must merge duplicate/clustered logbook rows.

## Open questions

- How to score the agent on clustered logbook rows (one incident, several entries).
- Whether to add CARE Farm B (400 MB, 6 anomaly events) as a held-out farm.

- Whether the fine-tuning step fits in the time budget or becomes a follow-up.

## Common rules (all five articles)

- **Source:** the idea comes from the video *"5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System"* (YouTube, 2026-09-28). Credit it in the article. The architecture here is ours; don't copy the video's code or diagrams.
- **Angle:** each article is a field report with runnable code, in the style of `2026-10-cnh-ocr-smithtune`: build it, measure it, show what broke.
- **Budget:** local first (M4 Pro 48 GB, mlx / Ollama). The cap for paid APIs is **US$10 per article**, set with `--max-cost` in the code; ask before any paid run.
- **Data:** public or synthetic only. No personal data. Record every dataset's license in `code/docs/DATA.md` before using it.
- **Numbers:** every number in the drafts comes from `code/docs/RESULTS.md`. Mark gaps with `[[RESULT: …]]` / `[[VERIFY: …]]`.
- **Deliverables:** EN long version + Medium short version, PT-BR, LinkedIn EN / PT-BR, code with tests + Makefile, `CONTEXT.md` glossary, ADRs for the hard decisions.
