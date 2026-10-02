# A disaster-risk agent that fuses signals it can't fully trust

**Status:** drafts complete (EN, EN Medium, PT-BR, LinkedIn EN / PT-BR); only the publication links are missing · **Branch:** `article/2026-11-disaster-risk-agent` · **Target date:** 2026-11-13

A replay, hour by hour, of the April–May 2024 Rio Grande do Sul floods (Taquari valley and Porto Alegre's Cais Mauá gauge) with only the data available at each hour: ANA river gauges and rain, INMET rain stations and Copernicus EMS flood maps become signals with a likelihood ratio, age and reliability, fused in plain Python into a calibrated probability that each gauge reaches its official flood level within 24 hours. A local Qwen3-8B agent writes the alert in Portuguese for civil defence, with no field for the number, and a deterministic audit checks what it writes. Findings: hand-set likelihood ratios missed four of five places, calibrated ones alerted 7–26 h before the flood-level crossing in 2024, at 3.23 false alarms per place-year out of sample; gauges went silent at the crest, and discounting a silent gauge made calibration worse; an LLM asked to do the fusion itself alerted earlier, but by alerting on hours with no flood within 24 hours (15–16 of 45, against 1 for the fusion). See [PLAN.md](PLAN.md), [code/docs/RESULTS.md](code/docs/RESULTS.md) and [code/docs/DATA.md](code/docs/DATA.md).

| | |
|---|---|
| Article (EN) | [article-en.md](article-en.md) |
| Article (EN, Medium short version) | [article-en-medium.md](article-en-medium.md) |
| Article (PT-BR) | [article-pt-br.md](article-pt-br.md) |
| LinkedIn | [EN](linkedin-en.md) · [PT-BR](linkedin-pt-br.md) |
| Code | [code/](code/) |
| Plan | [PLAN.md](PLAN.md) |

## Published

- Medium: [[LINK]]
- LinkedIn: [[LINK]]
