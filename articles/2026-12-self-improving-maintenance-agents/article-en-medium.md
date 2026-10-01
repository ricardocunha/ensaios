---
title: "Maintenance agents that learn from their own mistakes"
subtitle: "An LLM agent with episodic memory on a real wind farm's alarms and failure logbook: what memory changed, what it couldn't, and why 21 incidents can't prove it either way"
platforms: Medium (short version; the full version is article-en.md, for dev.to / Hashnode)
status: DRAFT — numbers final (code/docs/RESULTS.md), Brazil facts sourced in code/docs/DATA.md
repo: https://github.com/ricardocunha/ensaios/tree/main/articles/2026-12-self-improving-maintenance-agents
---

# Maintenance agents that learn from their own mistakes

The pitch for a "self-improving" maintenance agent is simple. The agent diagnoses an alarm, the logbook later says what really happened, the agent stores the lesson, and next time it does better. Nobody retrains anything; memory does the learning.

I wanted to know whether that works on real data, and how you would even tell. So I built one for a real wind farm, replayed 23 months of its alarms in time order, and compared three versions: **no memory**, **memory with no filter**, and **memory behind a gate**. The idea is project #5 of the video *"5 AI Agents Projects to Build in 2026"*; the architecture, code and numbers are mine.

The short version: the agent said "inspect" to every one of 77 alarms, with and without memory. I made one round of fixes, decided before re-running, and re-ran everything. It said "inspect" in 230 of 231 decisions. Memory changed one decision, on one episode. On this farm, with this model, memory didn't make the agent better, and 21 incidents couldn't have proved it if it had.

## Why Brazil's Northeast should care

In 2024 wind produced 107.7 TWh, 14.1 % of Brazil's electricity supply (EPE). The Northeast subsystem produced 92.2 % of the country's wind generation, and on one record day in August 2024 its wind farms produced 129 % of what the region consumed (ONS data, via ABEEólica).

Those farms generate exactly what this agent needs: 10-minute SCADA from every turbine and a maintenance log. But what's public is one level up. ONS publishes generation and wind speed per *plant*, not per turbine, and nothing says which component failed. The one public turbine-level SCADA I found from the Northeast, two coastal farms in 2013-14, has no failure log. So the data here is Portuguese, and the question becomes: what would an operator in Ceará or Rio Grande do Norte need to build this, and what should they expect?

## The data, and two traps

The turbines are EDP's "Wind Farm 1" in Portugal: five turbines, January 2016 to November 2017, 10-minute data, from the CARE to Compare benchmark (Wind Farm A) plus EDP's failure logbooks. Both are CC BY-SA 4.0. The logbook has 28 failure rows, merged into **21 incidents**. That is the whole ground truth.

- **The calendar was shifted.** CARE moves Farm A's timestamps to hide the source: +2191 days (+2192 for two files). Undoing it makes all 38 overlapping file pairs agree on 100 % of values, and lets me attach EDP's logbook at all.
- **A column was the answer.** Farm A's `status_type_id` looks like an operating state. Code 4 marks exactly the 14 days before each logbook entry. A detector using it would "predict" every failure. I use it nowhere.

## Detection: mostly a fight with the seasons

A naive Isolation Forest trained on the first 60 days learned winter and alarmed on summer: up to 70-74 % of days in July-August 2016. Two things fixed it: retraining every 30 days with the threshold set on recent unseen days, and scoring residuals of a normal-behaviour model per temperature instead of raw sensors.

At about one healthy alarm-day per turbine-month, the detector caught **7 of 18** evaluable incidents within 14 days. It can say *something is off*; it's poor at saying *what*. On the first alarm day, its top component group matched the logbook in only **1 of 22** pre-incident episodes. That gap is what the agent was for.

The detector produced **77 episodes**: 22 before an incident (covering 9 incidents), 29 false alarms, 26 near an incident, mostly after repairs.

## The agent, the memory, the gate

- **Agent:** Pydantic AI with Qwen3-8B running locally, three tools (residual series, context, maintenance log), all cut at the end of the first alarm day. It returns a typed diagnosis: which component, and *inspect*, *monitor* or *ignore*.
- **Memory:** one record per diagnosed episode: situation, diagnosis, and the logbook outcome, visible only once it would have been known.
- **Retrieval:** cosine similarity of first-day residual vectors. No embedding model.
- **Gate** (fixed before any run): outcome known, similarity ≥ 0.5, at most a year old, same turbine or component group, at most 3.
- **No look-ahead, tested:** change the future or cut it off, and every earlier prompt, tool result and decision must stay identical.

Before running any model, one number framed everything: in only **4** (ungated) and **1** (gated) of the 22 pre-incident episodes did a shown memory record a past failure of the component that later failed. Memory could rarely hand over the answer. If it helped, it would be by showing that similar alarms had led to nothing.

## Run 1: the agent never left "inspect"

77 episodes × 3 arms, 0 errors. The agent answered **"inspect" on all 77, in all three arms**, and named the detector's top group in 77, 71 and 72 of them. Component accuracy: 1, 2 and 1 of 22 (no memory, ungated, gated). It was the detector plus "inspect".

Memory did change the component in 9 episodes, always toward the generator bearing, the component that dominated the failures memory showed. The ungated arm's one extra hit (episode 45) came from three memories on another turbine, 8-9 months old, that the gate would have rejected. The same pull, elsewhere, gave a wrong answer.

The lesson was about the agent, not memory: with no cost on inspecting, "inspect" always looks safe. **Memory can't change a decision that never moves.**

## Run 2: one round of fixes, written down first

I allowed myself exactly one round, written into the plan before re-running:

1. **Memory as a track record.** Before individual memories, the prompt counts what followed similar alarms, using only outcomes known at that moment ("17 followed by a failure; 19 by nothing").
2. **Justify against the record.** If most similar alarms led to nothing and the agent still inspects, it must say what's different this time.
3. **Costs in the instructions.** Inspection ≈ 1; a failure a timely inspection would have caught ≈ 10; monitoring costs nothing now. An assumption from the domain, not fitted to this data.

I also re-ran the no-memory arm with the new prompt, to separate the prompt's effect from memory's.

| Arm | Prompt | Component right (of 22) | Not inspect on false alarm (of 29) | Input tokens / episode |
|---|---|---|---|---|
| no memory | v1 → v2 | 1 → 1 | 0 → 0 | 6.7k → 8.1k |
| memory, ungated | v1 → v2 | 2 → 2 | 0 → 0 | 9.3k → 10.7k |
| memory, gated | v1 → v2 | 1 → 1 | 0 → 0 | 7.7k → 7.8k |

Every pre-incident episode was inspected in every arm, both times. **The prompt alone changed nothing. Memory changed one decision out of 231.** The per-month learning curves lie on top of each other.

How the agent used the record is the interesting part:

- **Episode 73, the one change.** A transformer alarm two weeks after a "transformer fan damaged" repair. Gated record: 3 similar alarms, none followed by a failure. The gated agent chose *monitor*; the no-memory agent inspected. That's the call I'd make too. It happened once.
- **Episode 50, a justification that contradicts itself.** A false alarm; record: 2 similar alarms, both followed by nothing. The agent inspected because of "a higher detector score (2.9) compared to past alarms (2.6 and 2.9)" and a residual "+3.1 vs. +3.3 and +3.8". Both comparisons are false by its own numbers. My validator checked that the field was filled, not that it was true.
- **Episode 17, the record pointed the wrong way.** Record: 2 similar alarms, both followed by nothing. The agent inspected anyway, and a transformer incident followed. An agent that obeyed the record would have missed it.

When the gated record said "mostly nothing" (15 prompts), the agent overrode it 14 times.

And "inspect" isn't simply wrong here. **27 of the 77 alarms were followed by a logbook failure within 30 days.** With an inspection costing a tenth of a missed failure, inspecting every alarm is close to the expected-cost answer. The agent couldn't get better at *whether* to inspect, because "always" was already near optimal under my own cost assumption. Where it could have helped, naming the component, it copied the detector.

## What ~20 incidents can't tell you

None of this is a statistical result. 22 pre-incident episodes covering 9 incidents and 29 false alarms: a difference of one or two episodes between arms is within what a different seed, month or wording would move. What a case study can do is show the mechanism, episode by episode: what memory put in front of the agent, and whether the decision changed.

## What I'd tell a team

1. **Check whether the decision ever moves before you add memory.** If the no-memory arm gives the same answer to everything, no memory design can show a learning curve.
2. **Count the base rate before arguing about costs.** At a third of alarms preceding a failure and a 1 : 10 cost ratio, "inspect" is rational. Memory that teaches "most alarms are noise" helps only where they *are* noise.
3. **A required justification is a field, not a check.** Verify the reason in code, like you'd verify a quote.
4. **Gating made memory relevant and the prompt shorter, not the answers better.** Memories per prompt fell from 2.92 to 0.97; accuracy didn't improve.
5. **Ask for the data that would make this testable.** For Northeast operators: 10-minute SCADA plus a per-turbine failure log with component, timestamp and remark, kept for years. With a few hundred incidents instead of 21, the same harness would give an answer instead of a case study.

---

**Code, tests and every number:** [github.com/ricardocunha/ensaios › articles/2026-12-self-improving-maintenance-agents](https://github.com/ricardocunha/ensaios/tree/main/articles/2026-12-self-improving-maintenance-agents)

*Data: CARE to Compare Wind Farm A (Zenodo 15846963) and EDP's 2016/2017 failure logbooks, both CC BY-SA 4.0. Brazil figures: EPE, Balanço Energético Nacional 2025; ONS data via ABEEólica, Boletim Anual 2024. Idea: "5 AI Agents Projects to Build in 2026" (project #5).*

#AI #Agents #LLM #PredictiveMaintenance #WindEnergy #OpenSource #Brazil
