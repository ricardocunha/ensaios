# Plan: Maintenance agents that learn from their own mistakes

**Branch:** `article/2026-12-self-improving-maintenance-agents` · **Target date:** 2026-12-11 · **Video project:** #5 (self-improving wind turbine maintenance)

## Question

Does a maintenance agent actually get better when it keeps an episodic memory of past diagnoses and their outcomes, or does memory mostly add noise? And how would you prove it?

## Brazilian angle

Wind energy is a large part of the Northeast's grid. The data is a public wind-turbine SCADA dataset with recorded faults. [[VERIFY: candidates — EDP Wind Farm open data, Kelmarsh / Penmanshiel (Zenodo, CC-BY), CARE to Compare; licenses and fault labels]]

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

## Open questions

- Whether the fine-tuning step fits in the time budget or becomes a follow-up.

## Common rules (all five articles)

- **Source:** the idea comes from the video *"5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System"* (YouTube, 2026-09-28). Credit it in the article. The architecture here is ours; don't copy the video's code or diagrams.
- **Angle:** each article is a field report with runnable code, in the style of `2026-10-cnh-ocr-smithtune`: build it, measure it, show what broke.
- **Budget:** local first (M4 Pro 48 GB, mlx / Ollama). The cap for paid APIs is **US$10 per article**, set with `--max-cost` in the code; ask before any paid run.
- **Data:** public or synthetic only. No personal data. Record every dataset's license in `code/docs/DATA.md` before using it.
- **Numbers:** every number in the drafts comes from `code/docs/RESULTS.md`. Mark gaps with `[[RESULT: …]]` / `[[VERIFY: …]]`.
- **Deliverables:** EN long version + Medium short version, PT-BR, LinkedIn EN / PT-BR, code with tests + Makefile, `CONTEXT.md` glossary, ADRs for the hard decisions.
