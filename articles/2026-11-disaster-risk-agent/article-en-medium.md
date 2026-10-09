---
title: "A disaster-risk agent that fuses signals it can't fully trust"
subtitle: "Replaying the 2024 Rio Grande do Sul floods hour by hour: calibrated Bayesian fusion, an LLM that writes the alert but never computes it, and gauges that go silent at the crest"
platforms: Medium (short version; the full version is article-en.md, for dev.to / Hashnode)
status: DRAFT — replace every [[LINK]] before publishing
repo: https://github.com/ricardocunha/ensaios/tree/main/articles/2026-11-disaster-risk-agent
---

# A disaster-risk agent that fuses signals it can't fully trust

In late April and May 2024, rain fell for days over the rivers that drain into the Guaíba, in Rio Grande do Sul, Brazil. The Taquari valley flooded, and days later so did Porto Alegre. Defesa Civil RS counts 184 deaths and 25 people still missing (its last update, of April 2025); at the peak, in its bulletin of 23 May 2024, 581,643 people were displaced from their homes, not counting those in public shelters.

This isn't about what should have been done in those days. People on the ground worked under conditions no backtest reproduces. It asks a narrower question: **when rain gauges, river gauges, satellite maps and history disagree, and some of them stop reporting, how should an agent combine them into a flood alert it can explain? And would it have warned in time?**

I built one and replayed the event hour by hour, with only the data available at each hour. The idea is project #1 of the video *"5 AI Agents Projects to Build in 2026"*; the architecture, data and evaluation are my own. The model is **Qwen3-8B, run locally**, with no paid API.

The setup: river level and rain from ANA's telemetry (every 15 minutes), hourly rain from INMET stations, and Copernicus flood maps, turned into one signal per station per hour. A few lines of Python fuse them into a probability per place: *will this town's river gauge reach its official flood level in the next 24 hours?* An LLM agent writes the alert in Portuguese, and a deterministic audit checks what it wrote. Five places have a gauge and an official flood level: Muçum, Encantado, Estrela and Taquari in the valley, and Porto Alegre's Cais Mauá downstream.

![Pipeline diagram in four stages. Sources: ANA telemetry (15-minute river level and rain), INMET stations (hourly rain) and Copernicus EMS flood maps (EMSR720) feed a replay store that, at hour t, exposes only the data available up to t (store.as_of(t)). Each station yields one Signal per hour with source, value, LR, freshness and reliability. A Bayesian fusion in plain Python, in log-odds and calibrated on 2019-2022, outputs p(flood level within 24 h) and a risk level. Its fused state goes to the alert agent (Pydantic AI, local Qwen3-8B), which writes a headline and explanation in Portuguese with no number fields. A deterministic citation audit then checks numbers, stations, places, silent gauges and level.](images/pipeline.en.png)

## The data decided the scope

**The gauges go silent at the crest.** Every INMET rain station reported through the peak. Three of the five river gauges with a flood level didn't. In the six peak days (144 hours), Encantado had no level reading for 138 hours and Taquari for 108; Porto Alegre's Cais Mauá stopped at 23:15 on 05-02 (local time), three days before the Guaíba's 5.37 m crest, and never came back in the window. Telemetry never recorded Encantado's first-wave crest, which SGB, Brazil's geological survey, later surveyed at 23.14 m. It had happened before: Muçum's September 2023 record of 26.11 m is missing too.

**The satellite arrives after the peak.** The first Copernicus flood map was delivered 103.5 hours after the Estrela river level had become strong evidence of a flood (a likelihood ratio of 10 or more). It can confirm this flood; it can't warn of it.

**There's an official clock.** SGB's flood-warning service (SACE) publishes Taquari bulletins with upload times. The first of this event went out at 07:54 on 04-30 (local time). Civil-defence alerts are published one web page per notice, with no archive I could query, so the other reference is physical: the first gauge reading at or above each flood level.

The replay gives each signal adapter a snapshot of the data as of hour *t*, and nothing else. The tests inject a future spike and check that nothing earlier changes. A backtest that can see the future would make every number here worthless.

## Fusion: my intuition was off by an order of magnitude

Each signal carries a likelihood ratio (how much more likely this reading is if a flood is coming), the age of the reading, and a reliability. The fusion adds them up in log-odds, starting from each place's base rate, with weights fixed in advance. Rain stations in one storm share a single weight, because they aren't independent witnesses.

The base rates are tiny: 0.01 % to 1.3 % of hours in 2019–2022. With them, the round likelihood ratios I had picked by hand never put four of the five places on alert in 2024. So I kept each band's definition and fitted its ratio on 2019–2022 only. A gauge above its 90th percentile that rose a metre in six hours is worth about 32, not 3.

With the calibrated table, here's the first alert at each place in 2024, against the first flood-level reading:

| Place | Lead of the fusion's first alert | Hand-set ratios |
|---|---|---|
| Muçum | +25.75 h | never on alert |
| Encantado | +17.25 h | never |
| Estrela | +12.25 h | −0.75 h |
| Taquari | +20.25 h | never |
| Porto Alegre | +7.25 h | never |

Against SGB's first bulletin, a basin-wide warning, the fusion put Encantado and Estrela on alert about 11–12 hours earlier, and Muçum and Taquari within about 3 hours of it. That bulletin was a forecast for a whole basin; my fusion is one gauge's probability, in a replay, with a table fitted on earlier years. It shows the signals were there, not that anyone missed them. From 2019 to April 2024 it alerted before 20 of 22 flood onsets (those up to 2022 are in-sample for the fitted table), though in November 2023 SACE beat it at two places.

## The price, and the surprise

Early alerts cost false alarms. Out of sample (2023 to April 2024), the calibrated fusion raised **3.23 false alarms per place-year**, all near misses: the river peaked at a median 0.77 of its flood level. The hand-set rules raised none, because they almost never alert.

The ablations say where the skill comes from. With rain alone, nothing reached alert. Upstream gauges buy the lead at Taquari and Porto Alegre, and cause 14 of the 21 false alarms. Giving every signal the same weight (plain naive Bayes) alerts earliest, with 2.4 times the false alarms.

**The surprise: decaying a silent gauge's reliability made calibration worse.** I halved the trust in a reading every 6 hours of silence. Removing that improved the Brier score in 2024 (0.0927 vs 0.1148) and out of sample (0.0062 vs 0.0074), and changed no lead time. When a gauge goes silent in a flood, the river is usually still high; sometimes it went silent *because* the river was high. Silent isn't unknown.

## The LLM writes, in Portuguese, and never computes

The alert agent (Pydantic AI) gets the fused state as text and returns a headline, an explanation, the main drivers and the silent gauges. **It has no field for the probability or the level**: the alert copies them from the fusion, so the model can't round 88.8 % to 90 % and turn an alert into an emergency. It writes in Portuguese, for Brazilian civil defence.

A deterministic audit then checks the text: every number, station code and place must be in the input, every silent gauge must be named, and a stated risk level must be the fused one. In Portuguese, "3,66 m" and "3.66 m" are the same number.

Over 9 key hours in three output modes, the Portuguese alerts passed the audit **27 of 27** times. With English instructions, the mode that asks for JSON in plain text had failed twice, both times leaving out a silent gauge. Here's Porto Alegre at 03:00 local time on 05-03, fused probability 95.6 %, as generated (my English gloss below):

> **Porto Alegre: EMERGÊNCIA com 95,6% de probabilidade**
> A probabilidade combinada de 95,6% foi calculada com base no nível do rio em Porto Alegre (87450004) com efeito +4,52, que sem ele seria 19,1%. O nível do rio em Guaíba (87242000) contribuiu com efeito +2,12, reduzindo para 72,5% sem ele. Chuvas em Canela (A879) e Porto Alegre (A801) também elevaram a probabilidade. A régua 87450020 em Porto Alegre está silenciosa há 72 h e não contribuiu. Réguas 86950000 e 87450004 também estão desatualizadas e com menor peso.

*Gloss: "EMERGENCY, 95.6 %. Driven by Porto Alegre's river level (effect +4.52; 19.1 % without it) and the Guaíba level (+2.12; 72.5 % without it); rain at Canela and Porto Alegre also raised it. Gauge 87450020 has been silent for 72 h and did not contribute; gauges 86950000 and 87450004 are stale and weigh less."*

But passing isn't being right. Another text for the same hour said the silent upstream gauge "was not used", when it was, at low weight. One at Estrela gave Estrela's gauge code to Encantado. The audit checks *grounding*, not meaning: a real number or code in the wrong place passes. Reading the texts also found a bug in my own input, a silent gauge's "last reading" taken from its rain total, which no audit against that input could catch.

## What if the LLM did the fusion?

I gave Qwen3-8B the same per-hour signals the fusion sees, without the fused number, and asked for a probability and a level: 147 hours fixed in advance, three samples each, 441 calls.

On lead time before the flood-level crossing, it won: earlier alerts at four places, and Porto Alegre on alert 48 hours before its gauge reached the flood level. It didn't survive a closer look. Among 45 event hours with no flood in the next 24 hours, the LLM said alert or emergency 15–16 times per sample; the fusion, once. Its Brier score was worse (0.1938–0.1979 per sample vs 0.1469), and its probabilities collapsed onto a few values: 0.85, 0.92, 0.82 and 0.02 made up 299 of its 441 answers. It reads the evidence in roughly the right direction, but it can't hold a calibrated number or a fixed horizon.

## What I'd tell a team building this

1. **Audit the data before designing the agent.** The scope, the satellite's role and the hardest question (what a silent gauge means) came from the data.
2. **Calibrate likelihood ratios on history,** on years you then leave out, and measure the price in false alarms.
3. **Silence is information.** Name silent gauges in every alert, and test what your fusion does with them.
4. **Let the LLM write, not compute,** and audit what it writes, in its language, in code.
5. **Compare against the official clock, humbly.** A replay can show the signals were there; it can't show anyone should have acted sooner.

---

**Code, data pipeline and every number:** [github.com/ricardocunha/ensaios › articles/2026-11-disaster-risk-agent](https://github.com/ricardocunha/ensaios/tree/main/articles/2026-11-disaster-risk-agent)

*Data from ANA, INMET, SGB and the Copernicus Emergency Management Service; the repo doesn't redistribute it. A research backtest, not a warning system: in an emergency, follow Defesa Civil. Idea: "5 AI Agents Projects to Build in 2026" (project #1).*

#AI #Agents #LLM #Floods #DisasterRisk #Bayesian #OpenSource #Brazil
