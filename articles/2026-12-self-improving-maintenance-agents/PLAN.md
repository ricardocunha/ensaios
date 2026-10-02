# Plan: Can a maintenance agent learn from its own mistakes?

**Branch:** `article/2026-12-self-improving-maintenance-agents` · **Target date:** 2026-12-11 · **Video project:** #5 (self-improving wind turbine maintenance)

## Question

Does a maintenance agent actually get better when it keeps an episodic memory of past diagnoses and their outcomes, or does memory mostly add noise? And how would you prove it?

## Brazilian angle

Wind energy is a large part of the Northeast's grid. The data is a public wind-turbine SCADA dataset with recorded faults: CARE to Compare Wind Farm A (the EDP wind farm in Portugal) plus EDP's failure logbooks, both CC BY-SA 4.0. See `code/docs/DATA.md`.

**Decision (2026-09-30): keep the Brazil framing.** No public Brazilian turbine-level SCADA with fault labels was found, so the data stays Portuguese (EDP). The article says so plainly and frames the result for Brazil's Northeast wind operators: what a self-improving maintenance agent would need from their own SCADA and maintenance logs, and why opening that data would matter.

**Decision (2026-09-30, after milestone 2): "Option 2", a case study.** Keep this dataset (Farm A + EDP logbooks, 21 incidents) and frame the article as a case study. Show the memory mechanism and exactly what it changes on these incidents, episode by episode. Say plainly that ~20 incidents are too few to claim an improvement statistically. CARE Farm B is an optional replication check, only if time allows, and not part of milestone 3.

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

## Milestone 3 result (2026-09-30): agent + memory + replay harness

Details and every number: `code/docs/RESULTS.md` ("Milestone 3"). Full-run results: see the v1 and v2 sections below.

- **Agent.** Pydantic AI, typed `Diagnosis` {component, action inspect/monitor/ignore, urgency, evidence, confidence}. Three tools: residual series of any signal group, context (converter/nacelle residuals, other turbines' scores that day), maintenance log. Qwen3-8B 4-bit on the local mlx-lm server, thinking off, temperature 0.
- **Decision time = end of the first alarm day.** The m2 episode summary used the whole episode, which is later information, so the agent's view is rebuilt from day one. Detector-only component baseline at that time: 1 / 22 (3 / 22 over the whole episode).
- **Memory.** One record per diagnosed episode: first-day summary + residual vector, diagnosis, logbook outcome. The outcome is the first logbook row on the turbine within 30 days (known at its timestamp), or "no failure within 30 days" (known at day 31). Until then the memory says "not known yet". The memory never reads the scoring labels.
- **Retrieval:** cosine similarity of first-day residual vectors (sign·log1p|z|, 24 signals). No embedding model.
- **Gate** (`GatePolicy`, fixed before any model run): outcome known, similarity ≥ 0.5, ≤ 365 days old, same turbine or same top group, k ≤ 3. Every rejected candidate carries its reason. The ungated arm takes the top 3 by similarity with no filter.
- **No look-ahead, tested.** Changing the future (logbook rows, residuals, episodes) or cutting it off leaves every pre-split prompt, tool result, gate decision and diagnosis identical, in all three arms. Breaking the store or the tools' time cut makes the test fail. 67 offline tests.
- **What the gate does, independent of the model.** Memories per prompt: 2.92 ungated, 0.97 gated. Pre-incident episodes with any memory: 21 / 22 vs 8 / 22. Only 4 (ungated) and 1 (gated) of the 22 pre-incident prompts show a past failure of the component that later failed. On this farm, memory can rarely hand over the answer; its effect must mostly come from past alarms that led to nothing.
- **Smoke** (6 runs, 30 requests, shared server): tools and typed output worked every time. Median 18.8 s and about 11k input tokens per episode. All 6 answers were "inspect", including one false alarm; too few to call it a bias.
- **Queued full run:** `code/scripts/run_after_queue.sh`, 231 agent runs. It starts when the compliance queue writes `QUEUE_DONE` and shares the server with another queued article job. Expected: about 1.2 h at the smoke pace (231 × 18.8 s); allow up to 2 h, because memory prompts are longer and the other job shares the server.

## Milestone 3, v1 full run (2026-09-30)

Every number: `code/docs/RESULTS.md` ("Full run, m3 (v1)"). The agent answered "inspect" on all 77 episodes in all three arms. Component: 1 / 22 (none), 2 / 22 (ungated), 1 / 22 (gated). Not inspect on false alarms: 0 / 29 everywhere. The component was the detector's first-day top group in 77 / 71 / 72 of 77 episodes. Memory changed nothing measurable, because the decision never left its default. Kept as a result.

## Milestone 3, v2: one round of fixes (decided 2026-10-01, before any v2 run)

User-approved: **one** round of fixes, then a full re-run, then the write-up. No second round, whatever v2 shows.

**Diagnosis of v1.** The prompt gave the agent no reason to say anything but "inspect": inspecting had no cost, monitor/ignore were barely explained, and memory came as a list of individual stories, where one past failure reads louder than five past alarms that led to nothing. The fixes target those three things and nothing else. They do not change the detector, the episodes, the outcome rule, the similarity, the gate values or the scoring.

1. **Track record (memory shown as counts, then the individual memories).** `memory.track_record(candidates, query, policy)`: the pool is every visible past episode that passes the arm's gate rules **without** the k cap (gated: similarity ≥ 0.5, ≤ 365 days old, same turbine or same first-day top group; ungated: every past episode on the farm). It counts only outcomes known at decision time (`MemoryStore.visible(now)`): N known, k followed by a logbook failure on that turbine within 30 days (with the components), N − k followed by nothing, plus how many are still pending. Rendered as e.g. "7 similar past alarms with a known outcome: 2 were followed by a logbook failure within 30 days (generator_bearing 1, hydraulic_group 1); 5 were followed by nothing. 1 more is still pending." The top-3 memories follow as before. The `none` arm gets neither.
2. **Justification against the record.** The output gets one more field, `differs_from_record`. "The record says mostly nothing" = N ≥ 2 known outcomes and more than half followed by nothing. In that case an "inspect" answer must say, in that field, what in this episode differs from those alarms; an empty / "n/a" value is sent back once more with `ModelRetry` (an output validator, mechanical, no judgement on the content). Otherwise the field may be "n/a".
3. **Costs and the three actions in the instructions.** Stated as an assumption for the exercise, not measured on this farm: an inspection costs about one crew-day plus a few hours of stop (1 unit); a failure that a timely inspection would have caught costs about ten times that (unplanned downtime, crane and parts, secondary damage). Monitor = no work order, costs nothing now; the detector keeps scoring every day and a new alarm brings the turbine back. Ignore = explained by something else (farm-wide weather or grid event, sensor artefact, normal behaviour after a repair). No probability threshold is given; the 1 : 10 ratio comes from the domain, not from this data. If this farm's base rate of failures after an alarm is high, inspecting often is the rational answer under these costs; we report that rather than change the costs.

**Runs.** Tag `m3v2`, prompt `v2`, all three arms (77 episodes each) on the same local server and model, sequentially, `--resume`. The `none` arm with the v2 prompt separates the prompt effect (v1 none → v2 none) from the memory effect (v2 none → v2 ungated / gated). A 2-episode plumbing check runs first; the prompt is changed after it only for a technical failure (schema, tool errors), never for its answers.

**Guard rails.** Prompts were designed without per-episode labels (the v1 tables above were already written). No-look-ahead tests must pass for the v2 prompt in all arms; new tests check that the track record counts only outcomes known at decision time and does not move when the future changes.

## Milestone 3, v2 result (2026-10-01)

Every number: `code/docs/RESULTS.md` ("Full run, m3 (v2)"). The fixes did not move the decision: "inspect" in 230 of 231 runs; component 1 / 2 / 1 of 22 (none / ungated / gated), as in v1; not inspect on false alarms 0 / 29 everywhere. The only changed action is gated episode 73 (near incident, monitor after a transformer repair). The gated record said "mostly nothing" in 15 prompts and was overridden in 14, once with a self-contradicting justification (episode 50). Under the stated 1 : 10 costs and a farm where 27 of 77 alarms precede a logbook failure, "inspect" is close to the expected-cost answer. No second round (as decided). Draft: `article-en.md`.

## Open questions

- ~~How to score the agent on clustered logbook rows~~: score on incidents (milestone 2 rule). Keep the per-row remarks in the agent's view.
- ~~Should the agent be told about recent maintenance?~~ Yes (milestone 3): the `maintenance_log` tool returns logbook rows recorded before the decision time, as an operator would know them.
- CARE Farm B (400 MB, 6 anomaly events): optional replication check, only if time allows (after milestone 4).

- Whether the fine-tuning step fits in the time budget or becomes a follow-up.

## Common rules (all five articles)

- **Source:** the idea comes from the video *"5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System"* (YouTube, 2026-09-28). Credit it in the article. The architecture here is ours; don't copy the video's code or diagrams.
- **Angle:** each article is a field report with runnable code, in the style of `2026-10-cnh-ocr-smithtune`: build it, measure it, show what broke.
- **Budget:** local first (M4 Pro 48 GB, mlx / Ollama). The cap for paid APIs is **US$10 per article**, set with `--max-cost` in the code; ask before any paid run.
- **Data:** public or synthetic only. No personal data. Record every dataset's license in `code/docs/DATA.md` before using it.
- **Numbers:** every number in the drafts comes from `code/docs/RESULTS.md`. Mark gaps with the RESULT / VERIFY placeholders described in CONTRIBUTING.md.
- **Deliverables:** EN long version + Medium short version, PT-BR, LinkedIn EN / PT-BR, code with tests + Makefile, `CONTEXT.md` glossary, ADRs for the hard decisions.
