# Plan: Maintenance agents that learn from their own mistakes

**Branch:** `article/2026-12-self-improving-maintenance-agents` · **Target date:** 2026-12-11 · **Video project:** #5 (self-improving wind turbine maintenance)

## Question

Does a maintenance agent actually get better when it keeps an episodic memory of past diagnoses and their outcomes, or does memory mostly add noise? And how would you prove it?

## Brazilian angle

Wind energy is a large part of the Northeast's grid. The data is a public wind-turbine SCADA dataset with recorded faults: CARE to Compare Wind Farm A (the EDP wind farm in Portugal) plus EDP's failure logbooks, both CC BY-SA 4.0. See `code/docs/DATA.md`.

**Decision (2026-09-30): keep the Brazil framing.** No public Brazilian turbine-level SCADA with fault labels was found, so the data stays Portuguese (EDP). The article says so plainly and frames the result for Brazil's Northeast wind operators: what a self-improving maintenance agent would need from their own SCADA and maintenance logs, and why opening that data would matter.

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

## Milestone 2 result (2026-09-30)

Details and every number: `code/docs/RESULTS.md` ("Milestone 2").

- **Features.**
  - Normal-behaviour residuals: one gradient-boosted model per temperature, predicting the rise over ambient from ambient temperature, wind, power, rotor rpm and past 6 h / 24 h power. The model runs on hourly means.
  - Signals are grouped by component: generator, generator bearing, gearbox, hydraulic, hub, transformer (+ converter/nacelle as context). Detectors score days.
  - Farm A has no pressure signals.
- **Walk-forward.**
  - Retrain every 30 days on all data before the cutoff. Thresholds come from the last ≥ 21 days, which the model has not seen.
  - Training drops only the windows around faults already logged. `status_type_id` is never used.
  - A test proves that scores before a date do not change when anything after it changes.
  - 2016 incidents are now scored too: 18-19 of the 21 incidents are evaluable, against 11 of 28 rows in milestone 1.
- **Incidents.** 28 logbook rows → 21 incidents (same component ≤ 45 d apart, or any component ≤ 7 d apart).
  - **Timestamps mark stops.** 12 rows are trips within the same 10-minute row, and 8 fall at the end of an existing stop. This answers the timestamp question left open in milestone 1, from our reading of the SCADA.
- **Detectors at a matched budget of ≤ 1 healthy alarm-day per turbine-month**, hits at 14 d out of 18 evaluable incidents:

  | Detector | 14-d hits (seeds 0/1/2) | Quiet-window rate | p | Farm-wide alarm dates |
  |---|---|---|---|---|
  | Isolation Forest on residuals | **7 / 7 / 7** | 0.18-0.20 | 0.03-0.06 | 3-4 |
  | Raw Isolation Forest | 4-6 | 0.14-0.17 | | 12-13 |
  | Per-signal residual threshold | 5 | 0.22 | 0.35 | |

  The per-signal residual threshold does not beat chance.
- **Honest reading.**
  - Walk-forward retraining with recent calibration did most of the work against season. Residuals mainly remove farm-wide (weather/grid) alarms.
  - The margin between the two Isolation Forests is 1-3 incidents, which is within the noise.
  - Generator bearings are caught (4/5 at 14 d). Hydraulic (0-2/7) and gearbox (1/4) incidents mostly are not.
  - The top residual group matches the logbook component in only 3 of 22 pre-incident episodes. Diagnosis is where milestone 3 has to add value.
- **Hand-off to milestone 3.** `runs/m2_episodes.csv` holds 77 Isolation-Forest-on-residuals episodes and 66 threshold episodes, with turbine, dates, component group, top signals and context. It has no labels; the labels are in `runs/m2_episodes_eval.csv`.
  - Of the 77 Isolation Forest episodes, 29 are false alarms in healthy periods, 22 precede 9 incidents, and 26 sit near incidents, mostly after repairs.
  - That is a realistic mix for the agent.

## Open questions

- ~~How to score the agent on clustered logbook rows~~: score on incidents (milestone 2 rule). Keep the per-row remarks in the agent's view.
- Episodes after repairs (sensor replaced, generator swapped) look like strong anomalies. Should the agent be told about recent maintenance (logbook rows before the episode), as a real operator would know?
- Whether to add CARE Farm B (400 MB, 6 anomaly events) as a held-out farm.

- Whether the fine-tuning step fits in the time budget or becomes a follow-up.

## Common rules (all five articles)

- **Source:** the idea comes from the video *"5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System"* (YouTube, 2026-09-28). Credit it in the article. The architecture here is ours; don't copy the video's code or diagrams.
- **Angle:** each article is a field report with runnable code, in the style of `2026-10-cnh-ocr-smithtune`: build it, measure it, show what broke.
- **Budget:** local first (M4 Pro 48 GB, mlx / Ollama). The cap for paid APIs is **US$10 per article**, set with `--max-cost` in the code; ask before any paid run.
- **Data:** public or synthetic only. No personal data. Record every dataset's license in `code/docs/DATA.md` before using it.
- **Numbers:** every number in the drafts comes from `code/docs/RESULTS.md`. Mark gaps with `[[RESULT: …]]` / `[[VERIFY: …]]`.
- **Deliverables:** EN long version + Medium short version, PT-BR, LinkedIn EN / PT-BR, code with tests + Makefile, `CONTEXT.md` glossary, ADRs for the hard decisions.
