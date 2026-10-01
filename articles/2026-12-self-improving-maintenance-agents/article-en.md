---
title: "Maintenance agents that learn from their own mistakes"
subtitle: "An LLM agent with episodic memory on a real wind farm's alarms and failure logbook: what memory changed, what it couldn't, and why 21 incidents can't prove it either way"
platforms: Medium, dev.to, Hashnode
status: DRAFT — replace every [[RESULT: …]] / [[VERIFY: …]] before publishing
repo: https://github.com/ricardocunha/ensaios/tree/main/articles/2026-12-self-improving-maintenance-agents
---

# Maintenance agents that learn from their own mistakes

The pitch for a "self-improving" maintenance agent is simple. The agent diagnoses an alarm, the logbook later says what really happened, the agent stores the lesson, and next time it does better. Nobody retrains anything; memory does the learning.

I wanted to know whether that works on real data, and how you would even tell. So I built one for a real wind farm, replayed 23 months of its alarms in time order, and compared three versions: no memory, memory with no filter, and memory behind a gate. The idea is project #5 of the video *"5 AI Agents Projects to Build in 2026"*; the architecture, code and numbers here are mine.

The short version: the first run showed that memory can't fix an agent whose decision never moves. The agent said "inspect" to every one of 77 alarms, with and without memory. I then made one round of changes, decided before re-running, and re-ran everything. __V2_SHORT__

Every number below comes from the repo's `docs/RESULTS.md`.

## Why this matters for Brazil's Northeast

Wind is a large part of the Northeast's grid, and the farms there produce exactly the two things this agent needs: 10-minute SCADA from every turbine and a maintenance log. I looked for a public Brazilian dataset with both, turbine by turbine, and found none. [[VERIFY: ONS/ANEEL publish plant-level generation, not turbine SCADA with failures]] So the data here is Portuguese. The question it answers is what an operator in Ceará or Rio Grande do Norte would need to build this on their own data, and what they should expect from it.

## The setup

```
10-min SCADA ─► hourly temperatures minus ambient ─► normal-behaviour model per signal ─► residuals
                                                                                       │
                     Isolation Forest on residuals, retrained every 30 days ─► alarm days ─► episodes
                                                                                       │
  episode (first alarm day only) ─► agent (Pydantic AI, Qwen3-8B local) ─► Diagnosis{component, action, …}
          ▲                               │ tools: residual series · context · maintenance log (all cut at decision time)
          │                               ▼
  memory: (situation, diagnosis, outcome) ◄── outcome from the logbook, visible only once it would be known
          │
     gate: outcome known · similar · recent · same turbine or component group · at most 3
```

- **Detection** turns 10-minute sensor data into alarm episodes.
- **The agent** reads one episode as of the end of its first alarm day and answers with a typed diagnosis: which logbook component is failing (or none), and what to do: *inspect*, *monitor* or *ignore*.
- **Memory** stores each episode with the agent's diagnosis and, later, its outcome from the logbook.
- **The gate** decides which memories may enter the prompt.

## The data, and two things I had to fix before trusting it

The turbines are EDP's "Wind Farm 1" in Portugal: five turbines, 2016-01 to 2017-11, 10-minute data. The SCADA comes from the CARE to Compare benchmark (Wind Farm A, 158 MB). The labels come from EDP's failure logbooks for 2016 and 2017. Both are CC BY-SA 4.0.

The logbook has 28 failure rows: hydraulic group 8, generator 7, generator bearing 6, gearbox 4, transformer 3. Each row is a component, a timestamp and a free-text remark written by an operator. Some remarks are real failures ("Generator bearings replaced"), some are sensor issues ("Generator temperature sensor failure"), and several rows are one incident logged twice.

**Fix 1: the calendar.** CARE shifts Farm A's timestamps to hide the source. I found the shift by matching CARE's anomaly-event ends to logbook timestamps: +2191 days, and +2192 for two of the files. With the raw CARE calendar, 8 overlapping file pairs disagree (only 13-17 % of values match). After undoing the shift, all 38 overlapping pairs agree on 100 % of values. That also maps CARE's anonymous assets to EDP turbines, and that mapping is what lets me use EDP's logbook at all. CARE links only 11 of the 28 logbook rows to an event; all 16 failures of 2016 have none.

**Fix 2: a leak in the labels.** Farm A has a per-row `status_type_id`. It looks like an operating-state signal. It isn't: code 4 marks exactly the 14 days before each logbook entry, and code 3 the 3 days after. A detector that used it as a feature would "predict" every failure. I use it nowhere.

One more thing the SCADA told me: **the logbook timestamp marks a stop, not the start of degradation.** At 12 of the 28 timestamps the turbine trips within the same 10-minute row; 8 more fall at the end of an existing stop. So every detection window ends the day before the logged date.

Logbook rows were merged into **21 incidents** (same component within 45 days, or any component within 7 days). That is the whole ground truth: 21 incidents on 5 turbines.

## Detection: most of the work was against the seasons

A naive Isolation Forest on raw sensor averages, trained on the first 60 days, learned winter and alarmed on summer: up to 70-74 % of days in July-August 2016. Its "hits" before faults (21 of 24 at 14 days) meant little when 66 % of quiet windows had an alarm too.

What fixed it:

1. **Walk-forward retraining.** Retrain every 30 days on everything before the cutoff, and set the alarm threshold on the last 21+ days the model hasn't seen. A test proves that a day's score doesn't change when anything after it changes.
2. **Normal-behaviour residuals.** One gradient-boosted model per temperature predicts its rise over ambient from wind, power, rotor speed and recent load. The detector scores the residuals. This mostly removes farm-wide alarms (weather, grid): dates with 3+ of 5 turbines alarming fell from 12-13 to 3-4.

At a matched budget of at most one healthy alarm-day per turbine-month, the Isolation Forest on residuals caught **7 of 18** evaluable incidents within 14 days (all three seeds), against a quiet-window rate of 0.18-0.20. Generator bearings were caught (4 of 5); hydraulic (0-2 of 7) and gearbox (1 of 4) incidents mostly weren't.

The detector can say *something is off*. It is poor at saying *what*: the top residual group matched the logbook component in **3 of 22** pre-incident episodes. That gap is what the agent is for.

The detector produced **77 episodes**: 22 start within 30 days before an incident (covering 9 incidents), 29 start on a healthy day (false alarms), and 26 sit near an incident, mostly after repairs. That's the agent's workload, and a realistic one: most alarms are not followed by a failure.

## The agent, the memory and the gate

**Decision time is the end of the first alarm day.** The episode table from detection summarised whole episodes, up to 18 days long. That is later information. So the agent's view is rebuilt from the first day only, and its three tools (residual series of any component group, context such as the other turbines' scores, and the maintenance log) return only data before that moment. Seen this way, the detector's top group is right in **1 of 22** pre-incident episodes, not 3.

**Memory.** One record per diagnosed episode: the first-day summary and residual vector, the agent's diagnosis, and the outcome. The outcome comes from the logbook only: the first logbook row on that turbine within 30 days, known at its timestamp; otherwise "no failure within 30 days", known on day 31. Until then the memory says "outcome not known yet". The memory never reads the scoring labels.

**Retrieval** is cosine similarity of first-day residual vectors (24 signals, sign·log1p|z|). No embedding model: the situation *is* a vector of residuals.

**The gate** was fixed before any model run: outcome known, similarity ≥ 0.5, at most 365 days old, same turbine or same top component group, at most 3. The "ungated" arm takes the 3 most similar past episodes with no filter.

**No look-ahead, tested.** The test replays a synthetic farm three times: as is, with the future changed (logbook rows, residuals, an extra episode), and cut at a split date. Every prompt, tool result, gate decision and diagnosis before the split must be identical. Breaking the memory store or the tools' time cut makes it fail.

**What the gate does, before any model runs.** Ungated prompts carry 2.92 memories on average, gated ones 0.97. And here's the number that framed everything after: in only **4** (ungated) and **1** (gated) of the 22 pre-incident episodes does a shown memory record a past failure of the component that later failed. On this farm, memory can rarely hand the agent the answer. If it helps, it must help mostly from the other direction: by showing that similar alarms led to nothing.

## Run 1: the agent never left "inspect"

Qwen3-8B (4-bit) on a local mlx-lm server, thinking off, temperature 0. 77 episodes × 3 arms, 0 errors.

| Arm | Component right (of 22 pre-incident) | Inspect on pre-incident (of 22) | Not inspect on false alarm (of 29) | Appropriate (of 51) | Input tokens per episode |
|---|---|---|---|---|---|
| no memory | 1 | 22 | 0 | 22 | 6.7k |
| memory, ungated | 2 | 22 | 0 | 22 | 9.3k |
| memory, gated | 1 | 22 | 0 | 22 | 7.7k |
| detector alone (first day) | 1 | – | – | – | 0 |

The agent answered **"inspect" on all 77 episodes in all three arms**, at confidence 0.75-0.92. Its component was the detector's top group in 77, 71 and 72 of the 77 episodes. The agent was the detector plus "inspect".

Memory did change the component in 9 episodes, always in the same direction: toward `generator_bearing`. Generator bearings dominate the failures memory shows (44 of 70 failure memories in the ungated prompts), and the agent copied them. Twice that touched a scored episode:

- **Episode 45 (T09, Dec 2016), right for a weak reason.** The ungated arm switched from generator to generator bearing, which was correct. Its three memories were T07 episodes from April 2016, 245-274 days old, similarity 0.34-0.45, all followed by a T07 bearing failure. The gate would have rejected all three.
- **Episode 19 (T07, Jun 2016), the same pull, wrong.** A memory of a T09 bearing failure (similarity 0.77) moved the ungated arm from generator to generator bearing. The incident was a transformer.

The lesson of run 1 was about the agent, not memory: with no cost on an inspection and nothing that weighs "five similar alarms led to nothing" against "one led to a failure", inspecting is always the safe-looking answer. Memory can't change a decision that never moves.

## Run 2: one round of fixes, decided before re-running

I allowed myself one round, written into the plan before any new run, with no peeking at which episodes precede incidents:

1. **Memory as a track record.** Before the individual memories, the prompt now says what happened after similar past alarms, counting only outcomes known at decision time. For example: *"36 with a known outcome. 17 of them were followed by a logbook failure on that turbine within 30 days (generator_bearing 8, transformer 4, generator 3, gearbox 2); 19 were followed by nothing. 4 more are still pending."* The gated arm counts its own pool (the gate without the cap of 3); the ungated arm counts every past alarm on the farm.
2. **Justify against the record.** When most similar alarms led to nothing and the agent still chooses inspect, a new field must say what is different this time. An empty answer goes back to the model once more.
3. **Costs in the instructions.** An inspection costs about a crew-day (1); a failure a timely inspection would have caught costs about 10; monitor costs nothing now and the detector keeps watching. The ratio is an assumption from the domain, not fitted to this data.

I also ran the no-memory arm with the new prompt, to separate what the prompt did from what memory did.

__V2_RESULTS__

## What ~20 incidents can and can't tell you

None of the differences above is a statistical result. There are 22 pre-incident episodes covering 9 incidents, and 29 false alarms. A difference of one or two episodes between arms is within what a different seed, a different month or a reworded prompt would move. What this case study can do is show the mechanism, episode by episode: what memory put in front of the agent, and whether the decision changed. That is also what you'd need to look at on your own farm before trusting any curve.

## What I'd tell a team building this

__TAKEAWAYS__

---

*Idea from the video "5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System" (project #5, a self-improving wind-turbine maintenance agent). Data: CARE to Compare Wind Farm A (Zenodo 15846963) and EDP's 2016/2017 failure logbooks, both CC BY-SA 4.0. Code, tests and every number: [github.com/ricardocunha/ensaios › articles/2026-12-self-improving-maintenance-agents](https://github.com/ricardocunha/ensaios/tree/main/articles/2026-12-self-improving-maintenance-agents).*
