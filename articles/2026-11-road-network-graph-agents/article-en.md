---
title: "Graph agents that plan road maintenance"
subtitle: "Belo Horizonte's road network, 198,991 pothole requests, a knapsack solver and three Pydantic AI agents: what the LLM adds when tools do the graph math"
platforms: Medium, dev.to, Hashnode
status: DRAFT — ready for review (numbers checked against code/docs/RESULTS.md)
repo: https://github.com/ricardocunha/ensaios/tree/main/articles/2026-11-road-network-graph-agents
---

# Graph agents that plan road maintenance

A city has more potholes than money. Someone has to decide which streets get resurfaced this year and in what order, without closing two roads at once that together cut a neighbourhood off from its hospital. It sounds like a job for an agent: look at the network, weigh the trade-offs, write the plan.

I built that agent system on Belo Horizonte's real road network and a year of real pothole-repair requests, and compared it with a plain optimisation baseline. Deterministic tools do the graph math. The LLM only does the reasoning: which sections to add or drop, which works to schedule together, and how to explain the plan.

The result isn't what the architecture diagram promises. On this problem the solver already makes the plan, a simple heuristic does the scheduling better, and the LLM contributes explanation plus a small shift towards streets with more requests. The interesting parts are *how* it failed, and how much of its prose a number audit can actually vouch for.

Every number below comes from the repo's `code/docs/RESULTS.md`.

## The setup

![Pipeline diagram. OpenStreetMap (via OSMnx) gives a drive graph that is merged into road sections with sampled betweenness (k=2000); PBH Tapa-Buraco requests are snapped to the sections to give a condition score. Value is condition × criticality × km, with a synthetic cost. A greedy knapsack solver (within 1e-5 of exact) produces the solver plan; the maintenance agent adds or removes sections, each with a reason, and the solver rebuilds the plan; the closure agent puts 15 major works into 3 months with no access-cutting overlaps; the coordinator writes a quarterly plan with trade-offs from a tool-computed fact sheet; an audit with no LLM compares value with the solver, recomputes the schedule and looks up every number in the prose.](images/pipeline.en.svg)

- **Tools** are typed Python functions over NetworkX. They rank sections, solve the budget with forced adds or exclusions, compute what a set of closures does to 1,000 sampled trips and to hospital and school access, and score a whole schedule.
- **Agents** are Pydantic AI agents with typed outputs. The hand-off between them is plain code, not agent-calls-agent: fewer moving parts for a small model.
- **Model:** Qwen3-8B, 4-bit, on a local mlx-lm server, thinking off. It costs nothing per call, which matters when an evaluation is dozens of agent runs.

The idea comes from project #3 of the video *"5 AI Agents Projects to Build in 2026"*: road-network graph agents. The architecture and code here are my own.

## The graph: Belo Horizonte

I compared Porto Alegre and Belo Horizonte and chose Belo Horizonte, mainly for its data (next section). Its OSM drive graph has **32,311 nodes and 82,984 edges**. Travel times are OSMnx's free-flow estimates, so every delay below is a lower bound on what real traffic would do.

**Criticality** is travel-time-weighted edge betweenness: how many shortest paths run through a road. Exact betweenness on this graph would take an estimated 69–86 minutes on my laptop (the exact run hadn't finished after about an hour), so I sample **k=2000 source nodes** (321.1 s). On Porto Alegre, where the exact run did finish, k=2000 recovered 0.98 of the exact top-100 edges.

**Edges are the wrong unit.** The top edges are consecutive pieces of the same road, the Anel Rodoviário ring motorway. A city doesn't resurface an OSM edge; it resurfaces a stretch of street. So I merge consecutive edges with the same name and road class into **sections**, cut where a bigger road crosses and at 1 km. That gives **19,842 sections**, median length 163 m.

![Most critical road sections in Belo Horizonte](figures/bh-critical-sections.png)
*Top 100 of 19,842 sections by sampled betweenness. Road data © OpenStreetMap contributors (ODbL), openstreetmap.org/copyright.*

The map shows the corridors you'd expect: the Anel and the big radial avenues. But betweenness is not closure impact. Closing the top Anel section delays 112 of 1,000 sampled trips by a mean of 42.5 s. Closing a section of Avenida Quatro Mil Cento e Setenta e Dois, only the 8th road on the list, delays 111 trips by a mean of **388.9 s**, because there's no good detour. So closure impact gets its own tool call; you can't read it off a ranking.

## The pothole data, and what it really measures

Belo Horizonte publishes its citizens' service requests (BH Digital) as open data under CC-BY, with coordinates. The pothole-repair service is called *Tapa-Buraco*. From August 2022 to July 2023, the newest month published, there are **198,991 requests** at **88,942 distinct locations**. **95.0%** of them snap to a drivable road within 30 m.

![Pothole-repair requests per km in Belo Horizonte](figures/bh-pothole-density.png)
*Tapa-Buraco requests, Aug 2022 – Jul 2023: distinct locations per km per section, smoothed. Shows where repairs are requested, not measured pavement condition. Road data © OpenStreetMap contributors (ODbL), openstreetmap.org/copyright. Requests: Prefeitura de Belo Horizonte, BH Digital, dados.pbh.gov.br, CC-BY.*

It's tempting to call this "road condition". It isn't. It measures **who reports**:

- Residential streets get **21.0** request locations per km; the Anel motorway gets **0.10**. Few people file a pothole request from a motorway, and in this window the Anel wasn't the city's road anyway: it was a federal highway maintained by DNIT until the city took over 22.4 km of it in June 2025.
- Condition and criticality are nearly unrelated (Spearman **−0.09**). The streets people complain about and the roads the network depends on are different streets.

So the **condition** score is a percentile of smoothed request density, and the **value** of fixing a section is condition × criticality × km. The **repair cost** is synthetic: pavement area, scaled by condition. I don't have the city's real costs, so cost is in "m² of resurfacing" units, not reais. That's a stated assumption, not a finding.

## The baseline: a knapsack that is already almost optimal

Given each section's value and cost, choosing what to fix within the budget is a 0/1 knapsack over **11,860 candidate sections**. Greedy by value per cost lands within 1e-5 of the exact optimum (SciPy/HiGHS), and it runs in a fraction of a second.

| Budget (share of total repair cost) | Sections | Value captured | Requests covered |
|---|---:|---:|---:|
| 5% | 445 | 54.43% | 5.36% |
| 10% | 952 | 70.24% | 10.89% |
| 20% | 1,997 | 83.98% | 21.65% |

Value is concentrated: 5% of the budget captures over half of it, because betweenness is heavy-tailed. The solver buys arterials that have some requests (Avenida Waldir Soeiro Emrich, Amazonas, Vilarinho, Cristiano Machado, Tancredo Neves), not the residential streets with the most requests. That gap, only 5.36% of requests covered at a 5% budget, is where I expected an agent's judgment to matter.

There's a second deterministic bar. The plan's **15 most critical sections** are "major works" that close the road while they run. They have to go into the quarter's 3 months, at most 5 per month. A **violation** is a month whose works, closed together, cut hospital (10 min) or school (5 min) access that no single work cuts on its own. Two deterministic schedules set the bar:

- **Naive** (priority order): 1 violation at every budget, from the same pair each time: Anel section S00102 and Avenida Presidente Antônio Carlos section S01395 in the same month (at 20%, two Waldir Soeiro Emrich sections conflict in that month too).
- **Heuristic** (pairwise conflict check, greedy fill, swaps, no LLM): **0 violations**, and a worst month 17–27% lower than the naive one.

## The agents

**Maintenance agent.** It sees the solver plan and can propose adds and removes, each with a reason. It never builds the plan itself: the solver rebuilds it with the adds forced in and the removes excluded, so budget feasibility is never the LLM's job. A validator rejects unknown ids, "adding" sections that are already planned, and infeasible sets. Tools: `rank_sections`, `get_section`, `try_plan`.

**Closure agent.** It gets the 15 major works and assigns them to months. Tools: `check_schedule` (scores a whole schedule and names the conflicting pairs), `closure_impact` and `accessibility_loss`. It must copy each month's numbers from the tools and flag every month that loses access.

**Coordinator.** It gets a fact sheet computed by the tools (plus the other agents' reasons) and writes the quarterly plan with its trade-offs. It's told to use only numbers from the fact sheet.

**The audit.** None of it uses an LLM:
- value, budget and request coverage against the solver;
- the agent's schedule rescored by the same exact tool, against the naive and heuristic schedules;
- every number the closure agent states per month, recomputed from scratch;
- every number in the prose, looked up in a **ledger** of all the numbers the tools returned and the prompts showed. The agents' own text never enters the ledger, so a claim can't ground itself.

I ran the pipeline **3 times at each of 3 budgets** (5%, 10%, 20%) with the same inputs: 9 pipelines, 37 minutes in total on the shared local model server.

## Results

### The maintenance agent: small coverage gains, paid for in value

It completed 8 of 9 runs. The one failure fell back to the solver plan.

| Budget | Value vs. solver (3 runs) | Requests covered, agent | Requests covered, solver |
|---|---|---|---:|
| 5% | 95.44 / 99.74 / 93.78% | 6.11 / 5.33 / 6.40% | 5.36% |
| 10% | 97.42 / 100.00* / 99.41% | 10.99 / 10.89* / 11.97% | 10.89% |
| 20% | 99.98 / 99.99 / 99.98% | 21.62 / 21.61 / 21.62% | 21.65% |

\* the agent failed; the solver plan stands.

Every deviation costs value, as the objective guarantees. What the agent buys with it is a shift towards the streets people complain about. The three runs that added the most-requested residential streets (Rua Joviano Coelho with 509 requests, Rua das Verbenas with 358, …) gained **0.75 to 1.08 points of request coverage** for 0.6–6.2% of the value. At 20% it added high-value sections instead, and coverage went down slightly.

That's a real preference: fix what citizens report. But you could put it in the solver's objective as one weight and get the same answer every time. I didn't test that here.

The agent also gave different answers on reruns. The mean pairwise Jaccard of its deviations was **0.137** at 5%, **0.000** at 10% and **0.867** at 20%. At 10%, the two successful runs didn't share a single deviation. The final plans still stay close to each other (Jaccard 0.951–0.997), because the solver refills the budget around whatever the agent forces.

It also ignored a limit it was given. The instructions say at most 6 deviations. 4 of the 8 accepted proposals had 10–12, and in 6 of 9 runs the schema rejected a proposal with 15–20. Its one failure was two such rejections in a row.

### The closure agent: 1 of 9

This is the main finding. The closure agent produced a schedule in **1 of 9 runs**. I didn't tune it after the full run, because how it fails is more useful than another prompt revision.

**6 of the 8 failures come from one malformed id.** Rua Juarez Teixeira Pinto, section **S10128**, is a major work at every budget. It's the only work id that doesn't start with `S0`. In the first tool call of 6 runs, the model wrote it as **`S010128`**, as if every id had to look like `S0xxxx`. The tool answered `unknown section ids: ['S010128']`. In 4 of those runs the model sent the identical arguments again until its 3 retries ran out. In the other 2 it changed something else (it fixed a second bad id, or wrote `S0128`), but it never typed `S10128`.

**The other 2 failures are loops.** Both got `VIOLATION (pairs that conflict: S00102 + S01395)` back from `check_schedule`. One run kept that pair in month 1 for all 14 calls. The other separated it and created a new conflict in month 2. Both ended up sending **the same schedule 8 times** until they hit the request limit of 14, despite an instruction not to re-check a schedule. Many of those schedules weren't even valid: works listed twice, others missing. My `check_schedule` tool scored them anyway, because only the final output validator checks completeness. That's a tool-design gap on my side.

Across all 9 runs the agent called only `check_schedule`. It never used `closure_impact` or `accessibility_loss`, although the instructions ask for them.

**The one success** avoided the violation, and all its numbers were right (12/12 month fields, 6/6 access flags). But it put the Anel, two Antônio Carlos sections, Dom Pedro I and the 388.9-second Avenida Quatro Mil Cento e Setenta e Dois section in the same month:

| Schedule (same 15 works) | Violations | Worst-month delay | Hospital nodes losing access, per month |
|---|---:|---:|---|
| Naive | 1 | 58,766.9 s | 20 / 9 / 14 |
| Heuristic (no LLM) | **0** | **51,731.9 s** | 16 / 13 / 13 |
| Agent | **0** | 66,627.6 s | 19 / 13 / 10 |

Its worst month is **28.8% worse than the heuristic's**, and 13.4% worse than the naive schedule's on the same works. All six of its access flags say "Consider detour plans for hospital/school access".

### The coordinator, and what a number audit can vouch for

The coordinator completed 9 of 9 runs, and its plans read well. The audit is where it gets interesting.

The strict audit found **227 of 253** prose numbers in the ledger (89.7%). The evaluation log doesn't store the ledger itself, so I rebuilt it by replaying the logged tool calls. The rebuilt ledger matched the logged size and the logged strict counts in all 9 runs. Then I classified each of the 26 misses and checked every classification by hand:

| Class | Count | Example |
|---|---:|---|
| Correct value, different notation | 20 | value per cost "3.789e-6", exactly the tool's value. My audit read 3 decimals from the mantissa: a bug in the audit |
| Correct, derived from tool numbers | 3 | "Value given up: 48.96%" = 100 − 51.04 |
| Copied from an earlier agent's text | 0 | |
| Unsupported | 3 | "207 pothole requests, which is 2.1% of all snapped requests" (true: 0.11%) |

If scientific notation is compared at its real precision and simple derived numbers are allowed (100 − x, or a ± b of two grounded numbers in the same text), the score is **250 of 253 (98.8%)**. The coordinator goes from 105/108 to **108/108**. All three unsupported numbers are the maintenance agent's claims about its own effect. One rationale says the deviations "improve the overall value capture by 3.77 percentage points (from 66.01% to 69.78%)". Its own `try_plan` call had shown 66.01%, a 4.2-point *loss* against the solver's 70.24%, and 69.78% appears nowhere.

Reading the texts showed the limit of any lookup audit. These numbers all passed, and all are wrong in meaning:

- The coordinator wrote that a plan "gave up 1.08% of all snapped requests compared to the unconstrained solver plan". The plan *gained* 1.08 points.
- Another plan called 99.98% a "similarity to the unconstrained solver plan". It's the value ratio.
- The maintenance agent said Rua Joviano Coelho's 509 requests are "5.36% of all snapped requests". 5.36% is the whole solver plan's coverage; the street's share is 0.27%. The lookup credited it because 5.36 is in the ledger.

So "every number is traceable to a tool" is reachable with an 8B model and a strict prompt. "Every sentence is right" is a different property, and a lookup can't check it. The structured audit, where the agent fills typed fields and code recomputes them, is the one I'd trust.

### The verdict

| | Solver + heuristic | LLM agents (Qwen3-8B) |
|---|---|---|
| Value captured | 54.43 / 70.24 / 83.98% | 93.8–100% of the solver's |
| Requests covered | 5.36 / 10.89 / 21.65% | −0.04 to +1.08 points |
| Schedule completed | 9/9 | 1/9 |
| Worst-month delay (the one comparable case) | 51,731.9 s | 66,627.6 s |
| Same answer on rerun | yes | deviation overlap 0.0–0.87 |
| Numbers traceable to tools | n/a | 89.7% strict, 98.8% with notation/derived |

On this problem the LLM adds **explanation and small shifts in request coverage, not better plans**. The knapsack already optimises the stated objective, so the agent can only trade value for some other goal, and it does that inconsistently. Scheduling is better done by the heuristic: it finished every time, never had a violation, and its worst month was lower.

That doesn't make the agent layer useless. A plan whose trade-offs are written out in plain language is something a city engineer can read and argue with, and the coordinator's numbers were traceable. But the decision itself belongs to the solver.

## What I'd tell a team building this

1. **Build the deterministic baseline first, and make the agent beat it.** Here a greedy knapsack and a small scheduling heuristic set a bar the LLM didn't reach. Without them, the agent's plans would have looked fine.
2. **If the agent's "judgment" is a preference, put it in the objective.** The one thing the maintenance agent kept wanting, more coverage of reported streets, is a weight in the solver: reproducible, explainable and free.
3. **Don't make the model type ids.** Six of eight closure failures were one id with a zero inserted. Give the model indices or names from a closed list, resolve them in code, and have the error say which id it probably meant.
4. **Make tools reject impossible inputs, and stop repeated calls in code.** My schedule tool happily scored schedules with missing works, and the agent sent the same call 8 times. An instruction not to repeat itself stopped neither.
5. **A number audit shows where a number came from, not whether the sentence using it is right.** Keep the strict score and the lenient one, read the texts anyway, and move every claim that matters into typed fields that code can recompute.
6. **Pothole requests measure reporting, not pavement.** Say so in the plan, and don't let a model treat "most complaints" as "worst road".

---

*Idea from the video "5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System" (project #3, road-network graph agents). Code, data pipeline and every number: [github.com/ricardocunha/ensaios › articles/2026-11-road-network-graph-agents](https://github.com/ricardocunha/ensaios/tree/main/articles/2026-11-road-network-graph-agents). Road data © OpenStreetMap contributors (ODbL). Pothole requests: Prefeitura de Belo Horizonte, BH Digital, CC-BY; the figures show only per-section aggregates, never single requests. Repair costs are synthetic and travel times are free-flow.*
