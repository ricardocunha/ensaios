---
title: "A disaster-risk agent that fuses signals it can't fully trust"
subtitle: "Replaying the 2024 Rio Grande do Sul floods hour by hour: calibrated Bayesian fusion of river gauges and rain stations, an LLM that writes the alert but never computes it, and what happens when the gauges go silent at the crest"
platforms: Medium, dev.to, Hashnode
status: DRAFT — replace every [[LINK]] before publishing
repo: https://github.com/ricardocunha/ensaios/tree/main/articles/2026-11-disaster-risk-agent
---

# A disaster-risk agent that fuses signals it can't fully trust

In late April and May 2024, rain fell for days over the Taquari and the other rivers that drain into the Guaíba, in Rio Grande do Sul. The Taquari valley flooded, and days later so did Porto Alegre. Defesa Civil RS counts 184 deaths and 25 people still missing (its last update, of April 2025); at the peak, in its bulletin of 23 May 2024, 581,643 people were displaced from their homes, not counting those in public shelters. Muçum, Encantado and Estrela had already flooded in September and November 2023.

This article is not about what should have been done in those days. People on the ground did their work under conditions no backtest reproduces. It asks a narrower, technical question that the event makes concrete: **when rain gauges, river gauges, satellite maps and history disagree, and some of them stop reporting, how should an agent combine them into a flood alert it can explain? And would it have warned in time?**

I built one and replayed the event hour by hour, with only the data that was available at each hour. The idea comes from the video *"5 AI Agents Projects to Build in 2026"* (project #1, multi-signal disaster intelligence). The architecture, the data and the evaluation here are my own. Every number below comes from the repo's `code/docs/RESULTS.md`.

## The setup

```
ANA telemetry (15-min river level + rain) ─┐
INMET stations (hourly rain) ──────────────┤   replay: at hour t, adapters see only what
Copernicus EMS flood maps (EMSR720) ───────┘   was available at t (store.as_of(t))
                       │
        Signal{source, value, LR, freshness, reliability}   one per station per hour
                       │
        Bayesian fusion (plain Python, log-odds, calibrated on 2019-2022)
                       │                       ─► p(flood level within 24 h), risk level
        Alert agent (Pydantic AI, Qwen3-8B local) ─► headline + explanation in Portuguese, no number fields
                       │
        Citation audit (deterministic): numbers, stations, places, silent gauges, level
```

- **Scope:** the Taquari valley (Muçum → Encantado → Estrela → Taquari) as the main case, and Porto Alegre's Cais Mauá gauge on the Guaíba downstream (flood level 3.00 m, set by SEMA-RS, the state agency that operates the gauge): five places with a river gauge and an official flood level.
- **Hypothesis per place and hour:** *the place's gauge reaches its official flood level within the next 24 hours.* That's what the probability is about, and what it's scored against.
- **Model:** Qwen3-8B 4-bit on a local mlx-lm server, thinking off. No paid API.

## Part 1: the data audit decided the scope

Before writing any agent, I checked what can actually be downloaded for April–May 2024.

**What works without an account:** ANA's telemetry (river level and rain every 15 minutes), INMET's automatic stations (hourly), the Copernicus Emergency Management Service's precomputed flood polygons for activation EMSR720 (all in the Taquari valley), and SGB's SACE hydrological bulletins for the Taquari. All of it is public government data. ANA allows reproduction with the source cited; INMET says its data are public and free to access; I found no licence text for SGB's bulletins. The repo cites every source and redistributes none of the data.

**What's blocked:** CEMADEN's rain-gauge history (a CAPTCHA on every download) and the S2iD disaster history (openly licensed, but the server rejects scripted downloads). I left both out rather than work around the protection.

Three findings shaped everything after that.

**The gauges go silent at the crest.** In an hourly table for 14 stations over 04-20 → 05-20, every INMET rain station reported through the peak. Three of the five river gauges with a flood level did not:

| Gauge | Peak days 05-01 → 05-06 (144 h): hours with no level reading | Longest silent run in the window |
|---|---|---|
| Muçum | 0 | 0 h |
| Encantado | 138 | 105 h |
| Estrela | 42 | 29 h |
| Taquari | 108 | 127 h |
| Porto Alegre, Cais Mauá | 93 | 429 h (to the end of the window) |

Telemetry never recorded Encantado's first-wave crest, which SGB later surveyed at 23.14 m. Cais Mauá stops at 23:15 on 05-02 (local time), three days before the Guaíba's 5.37 m crest. It had happened before: Muçum's September 2023 record of 26.11 m is missing too, so the historical maxima *understate* the floods. Any fusion has to treat "no reading" as a state with its own meaning, not as a zero.

**The satellite arrives after the peak.** There was no Sentinel-1 scene over Encantado, in the Taquari valley, before 05-08, and Sentinel-2 was clouded on 05-01. The first Copernicus EMS flood map was delivered at 19:29 UTC on 05-04, 103.5 hours after the Estrela river level had reached the band with a likelihood ratio of 10 or more. In the replay a map becomes visible at its *delivery* time and serves as a label. The satellite can confirm this flood; it can't warn of it.

**There's an official clock to compare against.** SGB's SACE archive lists every 2024 Taquari bulletin with its upload time: 43 in April–May, the first uploaded at 07:54 on 04-30 (local time). Defesa Civil's alerts are published one web page per notice, with no archive I could query, so the other reference is physical: the first ANA reading at or above each gauge's flood level. Getting those clocks right (ANA is local time, INMET is UTC and hour-ending) took more work than any model.

## Part 2: signals, freshness, and a replay that can't see the future

Each source has an adapter that turns its readings into a `Signal` at hour *t*: the value, a **likelihood ratio** (how much more likely this reading is if a flood is coming than if not), the age of the reading, and a **reliability** between 0 and 1.

River levels fall into bands from each station's own 2019–2024 record (p90, p99, official flood level), doubled for a 1 m rise in 6 hours. Rain uses 24 h and 72 h totals. A silent gauge keeps its last real value, with a reliability that halves every 6 hours, and becomes an explicit "missing" signal after 72 hours. Nothing is interpolated.

The replay gives each adapter `store.as_of(t)` and nothing else. The tests compare every signal against a dataset *truncated* at that step and inject a future spike to check that nothing earlier changes. A backtest that can see the future would make every number here worthless.

## Part 3: calibrated Bayesian fusion, and the leads it gets

Fusion is a few lines of plain Python. Per place and hour:

```
log_odds = logit(prior) + Σ  w_i · r_i · ln LR_i          p = sigmoid(log_odds)
```

The prior is the share of 2019–2022 hours in which the gauge reached its flood level within 24 hours: 0.01 % to 1.3 %. `r_i` is the reliability, including the freshness decay. The weights are fixed in advance: 1 for the own gauge, 0.5 per upstream gauge, and 1 for the whole rain group, split across its stations, because rain stations in one storm aren't independent witnesses. The levels were fixed before the backtest too: attention from 0.10, alert from 0.50, emergency from 0.90.

**My hand-set likelihood ratios didn't work.** With priors that small, the round numbers I had picked (a river at p99 = 4, at its flood level = 10) never put Muçum, Encantado, Taquari or Porto Alegre on alert in 2024. Estrela got there 45 minutes *after* the river crossed its flood level. So I kept each band's definition and fitted its likelihood ratio on 2019–2022 only: the share of flood hours in that band divided by the share of non-flood hours. The data disagreed with my intuition by an order of magnitude. A gauge above p90 that rose a metre in six hours is worth about 32, not 3. Even "rain, but below every band" turned out to be evidence *for* a flood (2.5–2.8), because floods follow wet weeks.

With the calibrated table, here's the first alert at each place in 2024, against the first flood-level reading:

| Place | Flood level crossed (local) | Fusion alert | Lead | Hand-set LRs |
|---|---|---|---|---|
| Muçum | 05-01 12:45 | 04-30 11:00 | **+25.75 h** | never on alert |
| Encantado | 04-30 14:15 | 04-29 21:00 | **+17.25 h** | never |
| Estrela | 04-30 08:15 | 04-29 20:00 | **+12.25 h** | −0.75 h |
| Taquari | 05-01 04:15 | 04-30 08:00 | **+20.25 h** | never |
| Porto Alegre | 05-02 13:15 | 05-02 06:00 | **+7.25 h** | never |

Against the official bulletins, the fair comparison is with SGB's first SACE bulletin, a basin-wide warning uploaded at 07:54 on 04-30. The fusion put Encantado and Estrela on alert 10.9 and 11.9 hours before it. Muçum and Taquari were within about 3 hours of it: the bulletin came 3.1 h before the Muçum alert and 0.1 h before Taquari's. I want to be careful here. SGB issued a forecast bulletin for a whole basin; my fusion gives a probability for one gauge, in a replay, with a table fitted on earlier years. It shows the signals were there, not that anyone missed them.

**Earlier floods.** From 2019 to April 2024, the calibrated fusion alerted before 20 of 22 flood onsets, including all 10 at the Taquari gauges in the out-of-sample period (2023 to April 2024), and 1 of the 2 out-of-sample onsets at Cais Mauá (the 2019–2022 onsets are in-sample for the fitted table). In November 2023, though, SACE beat it at Muçum (by 11 h) and Taquari (by 18 h). The hand-set table alerted before 4 of the 22.

## Part 4: false alarms, calibration and ablations

Early alerts have a price. In the out-of-sample period (2023-01 → 2024-04, 6.50 place-years), the calibrated fusion raised **21 false alarms, 3.23 per place-year**. The hand-set rules raised none, because they almost never alert at all. The false alarms were near misses: the river peaked at 0.39–0.96 of its flood level during them, with a median of 0.77. And 2023 was an unusually wet year in the valley.

**Calibration:** Brier score 0.0074 out of sample (skill 0.44 over climatology) and 0.1148 in 2024 (skill 0.66). Out of sample it's overconfident between 0.5 and 0.9 (hours at 0.60 flooded 29 % of the time; naive Bayes still double-counts correlated evidence). In 2024 it was underconfident below 0.9: the event was bigger than anything in the training years.

**Ablations** (2024 leads in hours before the flood-level crossing, rounded to the hour except for the full model; out-of-sample false alarms and Brier scores):

| Configuration | Muçum | Encantado | Estrela | Taquari | Porto Alegre | False alarms (per place-year) | Brier, out of sample | Brier, 2024 |
|---|---|---|---|---|---|---|---|---|
| full | +25.75 | +17.25 | +12.25 | +20.25 | +7.25 | 21 (3.23) | 0.0074 | 0.1148 |
| no river levels (rain only) | missed | missed | missed | missed | missed | 0 | 0.0124 | 0.3104 |
| no upstream gauges | +26 | +7 | +13 | −1 | −1 | 7 (1.08) | 0.0078 | 0.1609 |
| no INMET rain | −0 | +17 | +12 | +19 | −1 | 8 (1.23) | 0.0073 | 0.1429 |
| no freshness decay | +26 | +17 | +12 | +20 | +7 | 20 (3.08) | **0.0062** | **0.0927** |
| equal weights (plain naive Bayes) | +41 | +19 | +14 | +33 | +58 | 51 (7.84) | 0.0385 | 0.1343 |

River levels carry the system: with rain alone, nothing reached alert. Upstream gauges buy the lead at Taquari and Porto Alegre, and cause 14 of the 21 false alarms. Equal weights alert earliest, with 2.4 times the false alarms.

**The finding I didn't expect: freshness decay made things worse.** Removing it improved the Brier score in 2024 (0.0927 vs 0.1148) and out of sample (0.0062 vs 0.0074), and changed no lead time. When a gauge goes silent in a flood, the river is usually still high; sometimes it went silent *because* the river was high. Discounting its last reading throws away true evidence. Silent isn't unknown. I still name silent gauges in every alert; I just no longer think a fixed half-life models what silence means.

## Part 5: the LLM writes, it never computes

The alert agent is a Pydantic AI agent with a typed output: `headline`, `explanation`, `drivers`, `silent_gauges`. It gets the fused state as text, including each signal's effect in log-odds and "the probability without it". **It has no field for the probability or the level**: the final alert copies them from the fusion, so the model can't round 88.8 % up to 90 % and turn an alert into an emergency.

The alerts are written in Portuguese, because the people who would read them work for Brazilian civil defence. The input block is in Portuguese too, with decimal commas ("efeito +4,52; sem ele 19,1%"), so the model copies each number in the format it writes it.

A **deterministic citation audit** then checks the text: every number, station code and place must appear in the input, every silent gauge must be named, and any stated risk level must be the fused one. In Portuguese that means reading "3,66 m" and "3.66 m" as the same number, "1.355 cm" as a possible thousands group, and "risco de emergência" as a level.

I ran it on 9 key hours (each place's first alert, and its first hour at attention or above with its own gauge silent) in three modes, first with English instructions, then in Portuguese:

| Mode | Audit pass, English | Audit pass, Portuguese | Model requests (EN / PT) |
|---|---|---|---|
| tool output | 9 / 9 | 9 / 9 | 9 / 9 |
| tool output + retry on audit failure | 9 / 9 | 9 / 9 | 10 / 9 |
| prompted output (JSON in text) | 7 / 9 | 9 / 9 | 9 / 9 |

In English, both prompted failures were the same kind: a silent gauge listed in the `silent_gauges` field but never mentioned in the text, at the two hours with two or three silent gauges. In Portuguese, both hours passed. That's one run per hour at temperature 0, with a differently worded input, so I don't read it as "Portuguese is more reliable". It shows that the agent and the audit work in the language the alert would actually be read in.

Here's Porto Alegre at 03:00 local time on 05-03, fused probability 95.6 %, prompted mode, as generated:

> **Porto Alegre: EMERGÊNCIA com 95,6% de probabilidade**
> A probabilidade combinada de 95,6% foi calculada com base no nível do rio em Porto Alegre (87450004) com efeito +4,52, que sem ele seria 19,1%. O nível do rio em Guaíba (87242000) contribuiu com efeito +2,12, reduzindo para 72,5% sem ele. Chuvas em Canela (A879) e Porto Alegre (A801) também elevaram a probabilidade. A régua 87450020 em Porto Alegre está silenciosa há 72 h e não contribuiu. Réguas 86950000 e 87450004 também estão desatualizadas e com menor peso.

*Gloss: "Porto Alegre: EMERGENCY, 95.6 % probability. The Porto Alegre river level (87450004) has an effect of +4.52; without it, 19.1 %. The Guaíba level (87242000) adds +2.12; without it, 72.5 %. Rain at Canela and Porto Alegre also raised the probability. Gauge 87450020 has been silent for 72 h and did not contribute. Gauges 86950000 and 87450004 are also stale and weigh less."*

That's the sentence the English prompted run left out at this hour: the Taquari outlet gauge (86950000), which tells Porto Alegre what's coming down the river, had been silent for 18.2 hours. Here it's named.

The tool-mode text for the same hour also passed, and it's wrong in a way the audit can't see. It says "As réguas silenciosas 87450020 e 86950000 não foram usadas devido à ausência de leituras recentes" (*the silent gauges 87450020 and 86950000 were not used, for lack of recent readings*). But 86950000 *was* used, at reliability 0.12, and the city's own gauge, 87450004, appears only as the main driver, never as silent. It passes because a station code anywhere in the text counts as a mention.

So, three limits. The audit checks *grounding*, not *pairing* or meaning. In Portuguese, the tool mode gave Estrela's gauge code to Encantado and called two silent river gauges "rain stations" (the same text in both tool runs), and one prompted text called two upstream river levels "rain readings". None of these is an invented number, code or place. A scripted pairing check catches the code given to the wrong place (2 of 27 Portuguese texts, 0 of 27 English ones); the rest took reading. Second, an audit has to speak the model's language: an English-only number parser would have read the "1.355 cm" a Brazilian writes as 1.355. Third, the audit is only as good as its input. Reading the English texts, I found that at one hour my silent-gauge list showed Encantado's 24-hour *rain* total as its "last reading", because ANA uses the same code for rain and level. No audit against the same input can catch that. It's fixed, with a test; after the fix, that hour passed in all three modes, in both languages.

## Part 6: what if the LLM did the fusion?

Maybe an 8B model is simply good at this. So I gave Qwen3-8B the same per-hour snapshot the fusion sees (every signal's value, age, calibrated likelihood ratio, reliability, the gauges' thresholds, the silent gauges, the prior), but not the fused probability, and asked for a probability and a level. One fixed prompt for every hour, nothing tuned on outcomes. The hours were fixed before the first call: every 3 hours from 48 h before to 12 h after each place's 2024 crossing (105), the onsets of the fusion's 21 out-of-sample false alarms, and 21 random quiet hours matched by place. Three samples each at temperature 0.7: 441 calls, 0 errors.

**Lead time** before the flood-level crossing (first hour at alert or above, on the 3-hour grid, so the fusion's leads differ slightly from Part 3):

| Place | Bayesian fusion | LLM (all 3 samples agree) |
|---|---|---|
| Muçum | +24.75 h | +39.75 h |
| Encantado | +15.25 h | +18.25 h |
| Estrela | +12.25 h | +12.25 h |
| Taquari | +15.25 h | +30.25 h |
| Porto Alegre | +6.25 h | +48.25 h (already on alert at the first grid hour) |

On that table alone, the LLM wins. It doesn't survive the next one. The question was "flood level within 24 hours", and among the 45 event hours where the answer was no, the LLM said alert or emergency 15–16 times per sample; the fusion, once. At Porto Alegre it was on alert 48 hours ahead with the city's own gauge below its p90. In hindsight that looks prescient. Under the question it was asked, it was wrong.

| | Bayesian fusion | LLM (per sample) |
|---|---|---|
| Event hours with no flood within 24 h (45): at ≥ alert | 1 | 16 / 16 / 15 |
| Fusion false-alarm hours (21): at ≥ alert | 21 | 17 / 17 / 16 |
| Random quiet hours (21): at ≥ alert | 0 | 0 / 0 / 0 |
| Brier score, all 144 labelled hours | **0.1469** | 0.1979 / 0.1964 / 0.1938 |

The same near misses fool both; both stay calm on genuinely quiet hours. But the LLM is worse calibrated: 0.85, 0.92, 0.82 and 0.02 make up 299 of its 441 answers, and it never went above 0.98, even with the river over its flood level. It behaves like a classifier with a few confidence labels.

**Consistency** was better than I expected: a median spread of 0.03 across samples, and the alert decision changed in only 2 of 147 hours. But the stated level changed in 34 hours, the worst spread was 0.63 (0.85, 0.42 and 0.22), and in 4 answers the level didn't match the model's own probability.

So the comparison supports the split. The model reads the evidence in roughly the right direction, but it can't hold a calibrated number or a fixed horizon. The fusion does both, in code that can be tested and ablated.

## What I'd tell a team building this

1. **Audit the data before designing the agent.** The scope, the role of the satellite and the hardest design question (what a silent gauge means) all came out of downloading the data and checking its clocks, not out of the architecture.
2. **Calibrate likelihood ratios on history.** My intuitive round numbers were off by an order of magnitude and missed four of five places. Fit them on years you then leave out, and measure the price in false alarms.
3. **Silence is information.** The gauges failed exactly at the crests. Report silent gauges in every alert, and test what your fusion does with them. My freshness decay, the obvious design, made calibration worse.
4. **Let the LLM write, not compute.** Keep the probability out of its output schema, and check what it writes against what it was given, in code, in the language and number format it writes.
5. **Compare against the official clock, humbly.** A replay with a fitted table is not a forecasting service. It can show that the signals were there; it can't show that anyone should have acted on them sooner.

---

*Idea from the video "5 AI Agents Projects to Build in 2026: Full AI Architecture + 10X System" (project #1). Code, data pipeline and every number: [github.com/ricardocunha/ensaios › articles/2026-11-disaster-risk-agent](https://github.com/ricardocunha/ensaios/tree/main/articles/2026-11-disaster-risk-agent). Data from ANA, INMET, SGB and the Copernicus Emergency Management Service; the repo doesn't redistribute it. This is a research backtest, not a warning system: in an emergency, follow Defesa Civil.*
