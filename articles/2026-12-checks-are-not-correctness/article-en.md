---
title: "My agent checks passed. The answers were still wrong."
subtitle: "Four agent projects, one lesson: a check that something exists is not a check that it's right"
platforms: Medium, dev.to, Hashnode
status: DRAFT — replace every [[LINK]] before publishing
---

# My agent checks passed. The answers were still wrong.

Over three months I built four agent systems from the same video, *"5 AI Agents Projects to Build in 2026"*, each on Brazilian data and each with an open 8B model on a laptop:

- a **compliance reviewer** for public contracts ([article](https://github.com/ricardocunha/ensaios/tree/main/articles/2026-10-compliance-document-agents));
- a **flood-risk agent** replayed on the 2024 Rio Grande do Sul floods ([article](https://github.com/ricardocunha/ensaios/tree/main/articles/2026-11-disaster-risk-agent));
- **road-maintenance planners** on Belo Horizonte's street network ([article](https://github.com/ricardocunha/ensaios/tree/main/articles/2026-11-road-network-graph-agents));
- a **wind-turbine maintenance agent with memory** ([article](https://github.com/ricardocunha/ensaios/tree/main/articles/2026-12-self-improving-maintenance-agents)).

Every one of them got a deterministic check on the model's output, because I didn't trust the model. Every one of those checks worked as designed. And every one of them let wrong answers through, for the same reason.

## The pattern: the check proved existence, not correctness

**Compliance: real quotes, wrong point.** The reviewer had to quote its evidence, and code checked the quote was verbatim in the contract. An auditor agent tried to refute each reported violation, and its objection counted only with a verbatim counter-quote. The auditor caught every false alarm on clean text. It also disputed a third of the *real* violations (19 of 59), with quotes that exist in the contract and prove nothing. It "refuted" a contract term that broke the 5-year limit by quoting the term itself: "72 (setenta e dois) meses". The quote was real. The argument wasn't.

**Road planning: real numbers, wrong meaning.** Every number in the planners' prose was looked up among the numbers the tools had returned. After fixing my own audit's bugs, 98.8% were found. Reading the texts showed what "found" means: a street's 509 requests described as "5.36% of all snapped requests" (5.36% was the whole plan's coverage; the street's true share was 0.27%), a value that "increased from 54.43% to 48.36%", a gain described as a loss. Each number existed in a tool output. They were attached to the wrong things.

**Flood alerts: real gauges, wrong places.** The alert agent writes the text; code checks that every number, station code and silent gauge it mentions is in its input. In Portuguese, all 27 alert texts passed. One of them said "As estações de chuva em Encantado (86879300) e Encantado (86720000) estão desatualizadas" ("the rain stations at Encantado… are out of date"). 86879300 is the Estrela gauge, not Encantado, and both are silent *river* gauges, not rain stations. Every code in the sentence is in the input.

**Maintenance memory: a filled field, a false reason.** To stop the agent inspecting every alarm, I made it justify an inspection whenever similar past alarms had led to nothing, in a required field. It filled the field. In one episode it wrote that the alarm differed because of "a higher detector score (2.9) compared to past alarms (2.6 and 2.9)" and a residual of "+3.1 vs. +3.3 and +3.8". Both comparisons are false by its own numbers. The validator checked that the field wasn't empty.

Four domains, one failure: **each check confirmed that something exists (a quote, a number, a code, a justification) and said nothing about whether it was used correctly.** These checks are still worth having: they catch invented quotes, invented numbers and invented stations. But passing them is a floor, not a verdict.

## What held up: code decides, the model explains

The second pattern is the flip side. In all four projects, the decisions that held up were made by plain code, and the model was most useful explaining them.

| Project | Decided by code | Decided by the model |
|---|---|---|
| Compliance | Legal limits applied in code: false alarms on those two rules fell from 23 of 40 findings to 2 | The 8B model quoted "12 (doze) meses" correctly, then said it exceeds "5 anos" |
| Flood risk | Bayesian fusion: Brier score 0.147; alert with no flood within 24 h on 1 of 45 hours | LLM given the same signals: Brier 0.195; alert on 15–16 of those 45 hours |
| Road planning | Heuristic schedule: completed 9 of 9, no conflicting closures | Scheduling agent: completed 1 of 9; in that one, the worst month was 28.8% worse |
| Maintenance | — | The agent said "inspect" in 230 of 231 runs, with or without memory |

The maintenance row needs care. 27 of 77 alarms were followed by a real failure, so under my assumed cost ratio "inspect everything" is close to the right answer. The point isn't that the model was wrong there; it's that it never *changed its mind*, so the memory I built had nothing to work on.

## What I'd do differently from the start

1. **Check meaning, not just existence, where it's cheap.** Pair each number with the thing it describes and check the pair; check that a station code belongs to the place named next to it; check that a comparison in a "justification" is actually true. In the flood project, a code–place pairing check flagged 2 of the 27 texts the existence check had passed.
2. **Read the outputs.** Every failure above was found by reading texts that had passed. A sample read by a person is part of the evaluation, not a nicety.
3. **Move decisions into code before tuning prompts.** Limits, schedules, probabilities: if it can be computed, compute it, and give the model the result to explain.
4. **Treat a passed check as "escalate less", not "correct".** In the compliance project the checks decide what goes to a human; they never approve anything on their own.

None of this is a reason not to use agents. Each project ended with something useful: a reviewer that knows when to hand a contract to a person, alert texts that cite their evidence, plans with their trade-offs written out. It's a reason to be precise about what each check proves.

---

*All four projects, with code, data pipelines and every number: [github.com/ricardocunha/ensaios](https://github.com/ricardocunha/ensaios). The projects come from the video "5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System".*
