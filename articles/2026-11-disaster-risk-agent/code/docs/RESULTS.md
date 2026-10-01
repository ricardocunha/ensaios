# Results

Every number in the drafts must come from this file. Each section says which command produced it.
Times are UTC unless marked "local" (UTC-3).

## Milestone 2: dataset, signals, replay (2026-09-30)

### Hourly dataset (`make dataset` → `data/cache/hourly.csv`)

11,424 rows = 14 stations × 816 hours (72 h warm-up + the 744-hour window 2024-04-20 00Z → 2024-05-21 00Z).
Status of the primary variable per hour (ANA: level, 4 readings expected; INMET: rain, 1 expected):

| Station | Place | Window (744 h): ok / partial / missing | Longest silent run | Peak days 05-01 → 05-06 (144 h): ok / partial / missing |
|---|---|---|---|---|
| ANA 86510000 | Muçum | 744 / 0 / 0 | 0 h | 144 / 0 / 0 |
| ANA 86720000 | Encantado | 254 / 51 / 439 | 105 h from 05-01 01:00Z | 0 / 6 / 138 |
| ANA 86879300 | Estrela | 284 / 176 / 284 | 29 h from 05-17 11:00Z | 19 / 83 / 42 |
| ANA 86950000 | Taquari | 299 / 19 / 426 | 127 h from 05-02 12:00Z | 35 / 1 / 108 |
| ANA 87242000 | Guaíba (CatSul) | 744 / 0 / 0 | 0 h | 144 / 0 / 0 |
| ANA 87450004 | Porto Alegre, Cais Mauá | 314 / 1 / 429 | 429 h from 05-03 03:00Z (to the end) | 50 / 1 / 93 |
| ANA 87450020 | Porto Alegre, Gasômetro | 383 / 30 / 331 | 329 h from 04-20 00:00Z (not started) | 50 / 28 / 66 |
| INMET A840 | Bento Gonçalves | 744 / 0 / 0 | 0 h | 144 / 0 / 0 |
| INMET A882 | Teutônia | 742 / 0 / 2 | 1 h | 144 / 0 / 0 |
| INMET A837 | Soledade | 744 / 0 / 0 | 0 h | 144 / 0 / 0 |
| INMET A894 | Serafina Corrêa | 744 / 0 / 0 | 0 h | 144 / 0 / 0 |
| INMET A844 | Lagoa Vermelha | 743 / 0 / 1 | 1 h | 144 / 0 / 0 |
| INMET A879 | Canela | 744 / 0 / 0 | 0 h | 144 / 0 / 0 |
| INMET A801 | Porto Alegre | 741 / 0 / 3 | 1 h | 144 / 0 / 0 |

Every INMET station reported through the peak; three of five river gauges with a flood level did not.

### Station level thresholds (`make thresholds`; ANA record 2019-01-01 → 2024-04-19, local)

| Station | Level readings | Record from | p50 | p90 | p99 | p99.9 | Max (local time) | Official flood level |
|---|---|---|---|---|---|---|---|---|
| Muçum | 180,870 | 2019-01-01 | 175 | 407 | 1008 | 1980 | 2302 (2023-11-18 23:45) | 1800 |
| Encantado | 176,984 | 2019-01-01 | 197 | 335 | 832 | 1845 | 2073 (2023-09-04 22:15) | 1200 |
| Estrela | 105,534 | 2020-07-09 | 1293 | 1329 | 1703 | 2218 | 2765 (2020-07-09 04:00, first reading) | 1900 |
| Taquari | 80,193 | 2021-11-26 | 258 | 430 | 778 | 1243 | 1295 (2023-11-20 04:00) | 850 |
| CatSul Guaíba | 56,813 | 2020-05-04 | 85 | 160 | 236 | 257 | 275 (2023-11-22 08:30) | none found |
| Cais Mauá C6 | 172,729 | 2019-01-01 | 88 | 154 | 259 | 327 | 346 (2023-11-21 08:15) | 300 [[VERIFY]] |
| Gasômetro | 0 | — | — | — | — | — | — | none confirmed |

All values in cm. Telemetry misses real crests: Muçum's September 2023 record (26.11 m nivelled by SGB) is absent because the gauge's last level before a 3.8-day gap was 2179 cm at 2023-09-04 19:30 local.

### Rain bands in the historical record (scratch measurement, ANA gauge rain 2019-01 → 2024-04-19, hourly steps with a full 72 h window)

Share of hours falling in each rain LR band (rule in `signals/_rain.py`):

| Gauge | Hours | Rain coverage | LR 0.5 | LR 1 | LR 2 | LR 5 | LR 10 |
|---|---|---|---|---|---|---|---|
| Muçum | 46,394 | 0.978 | 75.63 % | 22.22 % | 1.94 % | 0.17 % | 0.04 % |
| Encantado | 46,394 | 0.952 | 77.06 % | 19.84 % | 2.63 % | 0.41 % | 0.06 % |
| Cais Mauá C6 | 46,394 | 0.930 | 81.04 % | 17.00 % | 1.79 % | 0.17 % | 0 |

Missing rain readings count as zero in this measurement.

### Reference times (`make reference`; local time, UTC-3)

SGB SACE Taquari: 43 bulletins in April–May 2024; 28 between 04-30 and 05-06 (the SGB technical note also says 28).
First bulletin: data time 2024-04-30 06:00, uploaded 07:54.

| Gauge | Flood level (cm) | First ANA reading ≥ flood level | First SACE bulletin printing level ≥ flood (data / upload) | Telemetry max in window | Longest level gap in the 72 h after crossing |
|---|---|---|---|---|---|
| Muçum | 1800 | 05-01 12:45 | 05-01 22:00 / 05-02 00:28 | 2557 at 05-02 07:30 | 0.2 h |
| Encantado | 1200 | 04-30 14:15 | 05-12 13:00 / 05-12 14:51 (no reading printed during the first wave) | 1873 at 05-12 22:00 (second wave; the first-wave crest of 23.14 m was not recorded) | 64.8 h |
| Estrela | 1900 | 04-30 08:15 | 04-30 10:00 / 04-30 11:49 | 3366 at 05-02 13:30 | 7.8 h |
| Taquari | 850 | 05-01 04:15 | 05-01 06:00 / 05-01 07:39 | 1376 at 05-02 08:45 | 43.5 h |
| Cais Mauá C6 | 300 [[VERIFY]] | 05-02 13:15 | — (no SACE for the Guaíba in 2024) | 369 at 05-02 23:15 (last reading; SGB crest 5.37 m on 05-05) | 62.0 h |

### Replay (`make backtest`, 744 hourly steps, 18,184 signals)

First replay hour at which a *single* warning signal reached LR ≥ 4 and LR ≥ 10 (no fusion yet):

| Signal | Place | LR ≥ 4 (local) | LR ≥ 10 (local) |
|---|---|---|---|
| ana_level 86510000 | Muçum | 04-30 11:00 | 05-01 13:00 |
| ana_level 86720000 | Encantado | 04-30 08:00 | 04-30 15:00 |
| ana_level 86879300 | Estrela | 04-30 04:00 | 04-30 09:00 |
| ana_level 86950000 | Taquari | 04-30 22:00 | 05-01 05:00 |
| ana_level 87242000 | Guaíba (CatSul) | 05-02 19:00 | 05-02 22:00 |
| ana_level 87450004 | Porto Alegre, Cais Mauá | 05-02 06:00 | 05-02 14:00 |
| ana_level 87450020 | Porto Alegre, Gasômetro | never (no thresholds) | never |
| ana_rain 86510000 | Muçum | 04-29 23:00 | 04-30 07:00 |
| ana_rain 86720000 | Encantado | 04-30 04:00 | 04-30 05:00 |
| ana_rain 86879300 | Estrela | 04-30 04:00 | 04-30 11:00 |
| ana_rain 86950000 | Taquari | 04-30 10:00 | never |
| ana_rain 87242000 | Guaíba | 04-30 08:00 | never |
| ana_rain 87450004 | Porto Alegre | 04-30 10:00 | 05-02 13:00 |
| inmet_rain A840 | Bento Gonçalves | 04-30 05:00 | 04-30 10:00 |
| inmet_rain A879 | Canela | 04-30 04:00 | 04-30 10:00 |
| inmet_rain A837 | Soledade | 04-30 18:00 | 05-01 12:00 |
| inmet_rain A894 | Serafina Corrêa | 05-01 12:00 | 05-01 19:00 |
| inmet_rain A801 | Porto Alegre | 04-30 08:00 | never |
| inmet_rain A882 | Teutônia | 05-12 08:00 | never |
| inmet_rain A844 | Lagoa Vermelha | never | never |

The hourly replay reports a crossing at the end of the hour that contains the reading, so it lags the 15-min crossing by up to 1 h (Estrela: reading 08:15, replay 09:00).

Level signal status during 05-01 → 05-06 (144 UTC hours): Muçum 144 fresh; Encantado 8 fresh / 102 stale / 34 missing (max age 71.5 h); Estrela 107 / 37 / 0 (max age 9.0 h); Taquari 36 / 71 / 37 (71.2 h); CatSul 144 fresh; Cais Mauá 51 / 71 / 22 (71.8 h); Gasômetro 79 fresh / 65 missing.

Copernicus EMS labels become visible at delivery: first one Guaporé DEL0 (image 05-04 09:48Z, delivered 05-04 19:29Z, 34.3 ha), Encantado DEL0 on 05-05 09:28Z (163.5 ha), Roca Sales DEL0 on 05-06 19:18Z (199.1 ha). The first label is delivered 103.5 h after the replay hour in which the Estrela level signal reached LR ≥ 10 (04-30 12:00Z).

### Clock checks (scratch measurements, 2024-04-20 → 05-20)

- ANA vs INMET rain, best shift of ANA time towards UTC (Pearson r): Cais Mauá–A801 +2:45 (0.95; 0.42 at 0 h); CatSul–B807 +2:15 (0.93); CatSul–A801 +2:30 (0.91); Muçum–A840 +1:30 (0.86); Estrela–A882 +2:30 (0.58); Muçum–A894 +2:15 (0.54); Encantado–A882 +3:15 (0.33).
- INMET radiation-weighted mean row label vs solar noon (UTC h): A840 15.88 vs 15.44; A882 15.75 vs 15.45; A801 15.89 vs 15.41.
- SACE bulletin levels equal ANA readings at the same local clock time (6 of 6 values on 04-30 06:00 and 05-01 22:00 where both had a reading; at 05-01 22:00 the bulletin printed Estrela 3015 cm while ANA has no Estrela reading).

## Milestone 3: fusion, backtest, alert agent (2026-09-30)

Command: `make evaluate` (`python -m disaster_risk.evaluate`, 73 s on the M4 Pro), output in `runs/m3/`
(`summary.json`, `fused_2024.csv`, `lr_table.json`, `key_hours.json`). Times are local (UTC-3) unless marked.

### Fusion formula (`fusion.py`)

Per place (the five gauges with an official flood level: Muçum, Encantado, Estrela, Taquari, Porto Alegre/Cais Mauá) and replay hour t:

    H(place, t)  = the place's gauge reads >= its flood level in (t - 1 h, t + 24 h]
    log_odds(t)  = logit(prior) + Σ_i w_i · r_i · ln LR_i          p(t) = sigmoid(log_odds)

- prior: share of labelled hours with H = 1 in TRAIN (2019-2022), add-one smoothed.
- r_i: signal reliability, which already contains the freshness decay (halves every 6 h after 1 h; 0 after 72 h).
- w_i (fixed a priori): own gauge level 1.0; each upstream/neighbour level gauge 0.5; rain group 1.0 split evenly over its N stations (1/N each), because rain stations in one storm are correlated.
- LR_i, two modes: **hand-set** = the milestone 2 round numbers; **calibrated** = each band keeps its definition but gets LR = P(band | H) / P(band | not H) from the 2019-2022 replay, pooled across places per (role, source, band), add-half smoothing, ≥ 20 records, clipped to [0.01, 1000] (`calibration.py`).
- Risk levels (fixed before the backtest): normal < 0.10 ≤ attention < 0.50 ≤ alert < 0.90 ≤ emergency.
- Silent gauge: a level gauge (own or upstream) whose latest reading is > 3 h old, or missing.

Place → signals: Muçum = own gauge + own rain + INMET A840/A894/A837/A844; Encantado adds Muçum level (upstream) and rain; Estrela: Encantado + Muçum upstream, A882; Taquari: Estrela + Encantado upstream; Porto Alegre: Taquari, CatSul Guaíba and Gasômetro levels (upstream/neighbour), ANA rain Cais Mauá/CatSul, INMET A801/A879/A882.

Historical replay (`history.py`): 2019-01-05 → 2024-04-19 local, 46,368 hourly steps, 973,728 signals, same adapters, INMET yearly files 2019-2024. TRAIN = up to 2022-12-31 (priors and LR table), TEST = 2023-01-01 → 2024-04-19 (1.30 years; contains the July, September and November 2023 floods). Station level thresholds (p90/p99) still come from the whole 2019-2024-04 record (milestone 2), so they are in-sample for TEST.

### Priors (TRAIN)

| Place | Hours with H = 1 / labelled | Prior |
|---|---|---|
| Muçum | 52 / 34,333 | 0.0015 |
| Encantado | 198 / 35,037 | 0.0057 |
| Estrela | 203 / 16,369 | 0.0125 |
| Taquari | 0 / 9,411 (record starts 2021-11) | 0.0001 |
| Porto Alegre (Cais Mauá ≥ 300 cm) | 25 / 32,178 | 0.0008 |

### Calibrated LR table (TRAIN; `runs/m3/lr_table.json`)

Band = the hand-set LR the adapter gave (level: 0.5 below p90, 1.5 ≥ p90, 4 ≥ p99, 10 ≥ flood level, ×2 for a 1 m rise in 6 h; rain: 0.5 dry, 1 none, 2/5/10 by 24 h/72 h totals).

| Role, source | Band (hand-set LR) → calibrated LR (n H=1 / n H=0) |
|---|---|
| own gauge level | 0.5 → 0.079 (33 / 116,672); 1.5 → 3.02 (96 / 8,809); 3 → 32.5 (39 / 335); 4 → 18.1 (24 / 374); 8 → 142 (56 / 109); 10 → 1000 cap (143 / 0); 20 → 1000 cap (63 / 0) |
| upstream level | 0.5 → 0.029; 1.5 → 1.96; 3 → 31.2; 4 → 112; 8 → 236; 10 → 110 (49 / 75); 20 → 468 (37 / 13) |
| ANA gauge rain | 0.5 → 0.067; 1 → 2.82; 2 → 20.2; 5 → 52.7; 10 → 133 (13 / 24) |
| INMET rain | 0.5 → 0.112; 1 → 2.46; 2 → 22.3; 5 → 79.1; 10 → 673 (16 / 5) |

The hand-set LRs were far too timid for priors of 0.01–1.3 %: the data says a rising river at p90 is worth ~30, not 3, and even the "no band" rain state (1) is evidence for H (2.5–2.8) because floods follow wet weeks.

### 2024 lead times (lead = flood-level crossing − alert onset; positive = alert first)

| Place | Flood-level crossing | Fusion attention | **Fusion alert (calibrated)** | Lead | Hand-set LRs: alert | Own gauge LR ≥ 10 (M2) | Lead | Any of the place's signals LR ≥ 10 | Lead |
|---|---|---|---|---|---|---|---|---|---|
| Muçum | 05-01 12:45 | 04-29 21:00 | **04-30 11:00** | **+25.75 h** | never (max p < 0.5) | 05-01 13:00 | −0.25 h | 04-30 07:00 | +29.75 h |
| Encantado | 04-30 14:15 | 04-29 20:00 | **04-29 21:00** | **+17.25 h** | never | 04-30 15:00 | −0.75 h | 04-30 05:00 | +9.25 h |
| Estrela | 04-30 08:15 | 04-29 19:00 | **04-29 20:00** | **+12.25 h** | 04-30 09:00 (−0.75 h) | 04-30 09:00 | −0.75 h | 04-30 05:00 | +3.25 h |
| Taquari | 05-01 04:15 | 04-30 02:00 | **04-30 08:00** | **+20.25 h** | never | 05-01 05:00 | −0.75 h | 04-30 09:00 | +19.25 h |
| Porto Alegre | 05-02 13:15 | 05-01 16:00 | **05-02 06:00** | **+7.25 h** | never | 05-02 14:00 | −0.75 h | 04-30 10:00 (Canela rain) | +51.25 h |

The replay is hourly and reports at the end of the hour, so any replay time lags a 15-min event by up to 1 h. "Any signal LR ≥ 10" fires early but is not an alert rule anyone could run: for Porto Alegre it is a rain station 51 h before the crossing, and single rain signals reach LR ≥ 10 at stations that never flooded (milestone 2 table).

Against the SGB SACE bulletins (upload times; SACE covers the Taquari gauges, not the Guaíba):

| Place | First SACE bulletin (upload) | Fusion alert − bulletin | First bulletin printing the station ≥ flood (upload) | Fusion alert − that bulletin |
|---|---|---|---|---|
| Muçum | 04-30 07:54 | bulletin 3.1 h earlier | 05-02 00:28 | alert 37.5 h earlier |
| Encantado | 04-30 07:54 | alert 10.9 h earlier | 05-12 14:51 (no Encantado reading printed in the first wave) | — |
| Estrela | 04-30 07:54 | alert 11.9 h earlier | 04-30 11:49 | alert 15.8 h earlier |
| Taquari | 04-30 07:54 | bulletin 0.1 h earlier (alert 08:00) | 05-01 07:39 | alert 23.7 h earlier |

The first SACE bulletin is a basin-wide warning, not a per-station flood call, so the fair comparison is: the fusion put Encantado and Estrela on alert about 11–12 h before SGB's first bulletin, and Muçum and Taquari within about 3 h of it.

### Historical floods: same fusion, same rule (TRAIN events are in-sample for the LR table; TEST events are not)

Flood onset = first reading ≥ flood level after 7 days below it. SACE column = first bulletin uploaded within ±72 h of the onset.

| Place | Onset | Split | Calibrated alert onset | Lead | Hand-set lead | First SACE upload (±72 h) | SACE lead | Alert − SACE |
|---|---|---|---|---|---|---|---|---|
| Muçum | 2020-07-08 03:30 | TRAIN | 07-07 21:00 | +6 h | missed | 07-07 21:01 | +6 h | +0 h |
| Muçum | 2023-09-04 16:45 | TEST | 09-04 13:00 | +4 h | missed | 09-04 14:51 | +2 h | +2 h |
| Muçum | 2023-11-18 09:15 | TEST | 11-17 23:00 | +10 h | missed | 11-17 11:36 | +22 h | −11 h |
| Encantado | 2019-11-05 09:00 | TRAIN | 11-05 00:00 | +9 h | missed | — | — | — |
| Encantado | 2020-07-07 23:00 | TRAIN | 07-06 06:00 | +41 h | missed | 07-07 21:01 | +2 h | +39 h |
| Encantado | 2022-05-04 01:45 | TRAIN | 05-01 18:00 | +56 h | missed | 05-03 17:14 | +9 h | +47 h |
| Encantado | 2023-07-13 04:15 | TEST | 07-12 18:00 | +10 h | missed | 07-13 00:20 | +4 h | +6 h |
| Encantado | 2023-09-04 15:00 | TEST | 09-04 06:00 | +9 h | −3 h | 09-04 14:51 | +0 h | +9 h |
| Encantado | 2023-11-18 02:15 | TEST | 11-16 14:00 | +36 h | −8 h | 11-17 11:36 | +15 h | +22 h |
| Estrela | 2020-07-09 04:00 | TRAIN | 07-07 18:00 | +34 h | +0 h | 07-07 21:01 | +31 h | +3 h |
| Estrela | 2022-05-03 10:00 | TRAIN | 05-02 01:00 | +33 h | missed | 05-03 17:14 | −7 h | +40 h |
| Estrela | 2022-05-30 11:15 | TRAIN | 05-29 18:00 | +17 h | missed | 05-30 08:19 | +3 h | +14 h |
| Estrela | 2022-06-07 08:00 | TRAIN | 06-06 12:00 | +20 h | missed | 06-06 23:21 | +9 h | +11 h |
| Estrela | 2022-06-23 06:30 | TRAIN | 06-22 05:00 | +26 h | missed | 06-22 18:41 | +12 h | +14 h |
| Estrela | 2023-07-13 06:15 | TEST | 07-12 18:00 | +12 h | +2 h | 07-13 00:20 | +6 h | +6 h |
| Estrela | 2023-09-04 18:30 | TEST | 09-04 06:00 | +12 h | +2 h | 09-04 14:51 | +4 h | +9 h |
| Estrela | 2023-11-18 01:45 | TEST | 11-16 14:00 | +36 h | +2 h | 11-17 11:36 | +14 h | +22 h |
| Taquari | 2023-09-05 14:30 | TEST | 09-04 16:00 | +22 h | missed | 09-04 14:51 | +24 h | −1 h |
| Taquari | 2023-11-18 15:30 | TEST | 11-18 06:00 | +10 h | missed | 11-17 11:36 | +28 h | −18 h |
| Porto Alegre | 2019-06-27 13:15 | TRAIN | — | missed | missed | — | — | — |
| Porto Alegre | 2023-09-27 08:30 | TEST | — | missed | missed | — | — | — |
| Porto Alegre | 2023-11-20 07:15 | TEST | 11-19 16:00 | +15 h | missed | — | — | — |

Calibrated fusion: 20 of 22 onsets had an alert before the crossing (all 10 TEST onsets at the four Taquari gauges, 1 of 2 TEST onsets at Cais Mauá). Hand-set: 4 of 22 with lead ≥ 0 h (all at Estrela), 2 more alerted after the crossing, 16 missed. September 2023 (the second event): Muçum +4 h, Encantado +9 h, Estrela +12 h, Taquari +22 h; the first SACE bulletin (uploaded 09-04 14:51) came after the fusion alert for Muçum (13:00), Encantado and Estrela (06:00), and 1 h before the Taquari alert (16:00). In November 2023 SACE was earlier than the fusion at Muçum (11 h) and Taquari (18 h).

### False alarms (alert episodes; episodes < 24 h apart are merged)

An episode is a false alarm when no reading ≥ flood level exists from its onset − 1 h to its end + 24 h while the gauge did report ("unverifiable" when it did not report at all).

| Fusion | Period | Place-years | Alert episodes: hits / false / unverifiable | False alarms per place-year |
|---|---|---|---|---|
| calibrated | TEST 2023-01 → 2024-04 | 6.50 | 11 / 21 / 1 | **3.23** |
| calibrated | TRAIN 2019-01 → 2022-12 (in-sample) | 19.95 | 10 / 19 / 3 | 0.95 |
| calibrated | 2024 window 04-20 → 05-20 | 0.42 | 9 / 0 / 0 | 0 |
| hand-set | TEST | 6.50 | 5 / 0 / 0 | 0 |
| hand-set | TRAIN | 19.95 | 1 / 0 / 0 | 0 |

Per place, calibrated TEST (hits/false/unverifiable): Muçum 2/3/0, Encantado 3/7/0, Estrela 3/9/1, Taquari 2/1/0, Porto Alegre 1/1/0.
The false alarms were near misses: the highest reading during a TEST false alarm was 0.39–0.96 × the flood level (median 0.77; TRAIN 0.35–0.98, median 0.73). 2023 was an unusually wet year in the valley; 3.23 per place-year is the price of the 7–36 h leads above. The hand-set LRs have no false alarms because they almost never alert.

### Calibration (Brier score over hours with a label; climatology = the prior)

| Fusion | TEST Brier (climatology 0.0132) | BSS | 2024 window Brier (climatology 0.3426) | BSS |
|---|---|---|---|---|
| calibrated | 0.0074 | 0.44 | 0.1148 | 0.66 |
| hand-set | 0.0111 | 0.16 | 0.2679 | 0.22 |

TEST: 52,675 labelled place-hours, 697 positive. 2024 window: 2,453 labelled place-hours of 3,720 (the rest had a silent gauge), 849 positive.

Reliability table, calibrated fusion (bin: n, mean p, observed frequency):

| Bin | TEST | 2024 window |
|---|---|---|
| [0, 0.01) | 49,421, 0.000, 0.001 | 1,583, 0.001, 0.098 |
| [0.01, 0.1) | 1,792, 0.040, 0.064 | 134, 0.046, 0.425 |
| [0.1, 0.3) | 672, 0.173, 0.107 | 100, 0.171, 0.410 |
| [0.3, 0.5) | 163, 0.398, 0.491 | 71, 0.404, 0.789 |
| [0.5, 0.7) | 136, 0.599, 0.294 | 81, 0.603, 0.728 |
| [0.7, 0.9) | 218, 0.800, 0.523 | 74, 0.827, 0.959 |
| [0.9, 1] | 273, 0.981, 0.894 | 410, 0.986, 1.000 |

In the TEST years the fusion is overconfident between 0.5 and 0.9 (naive Bayes still double-counts correlated evidence); in 2024 it is underconfident everywhere below 0.9 (the event was bigger than anything in TRAIN). Hand-set, 2024: every bin from 0.01 to 0.9 had observed frequency 0.83–1.00.

### Ablations (calibrated LR table; lead in h for the 2024 crossings; TEST false alarms and Brier)

| Config | Muçum | Encantado | Estrela | Taquari | Porto Alegre | TEST false (per place-year) | TEST hits / false / unverif. | Brier TEST | BSS TEST | Brier 2024 | BSS 2024 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| hand-set LRs | missed | missed | −0.75 | missed | missed | 0 (0.00) | 5 / 0 / 0 | 0.0111 | 0.16 | 0.2679 | 0.22 |
| **full** | +25.75 | +17.25 | +12.25 | +20.25 | +7.25 | 21 (3.23) | 11 / 21 / 1 | 0.0074 | 0.44 | 0.1148 | 0.66 |
| no ANA level (rain only) | missed | missed | missed | missed | missed | 0 (0.00) | 0 / 0 / 0 | 0.0124 | 0.06 | 0.3104 | 0.09 |
| no upstream level | +26 | +7 | +13 | −1 | −1 | 7 (1.08) | 9 / 7 / 0 | 0.0078 | 0.41 | 0.1609 | 0.53 |
| no ANA rain | +19 | +17 | +12 | +20 | +7 | 18 (2.77) | 11 / 18 / 1 | 0.0069 | 0.48 | 0.1228 | 0.64 |
| no INMET rain | −0 | +17 | +12 | +19 | −1 | 8 (1.23) | 11 / 8 / 0 | 0.0073 | 0.44 | 0.1429 | 0.58 |
| no freshness decay | +26 | +17 | +12 | +20 | +7 | 20 (3.08) | 12 / 20 / 1 | **0.0062** | **0.53** | **0.0927** | **0.73** |
| equal weights (all w = 1) | +41 | +19 | +14 | +33 | +58 | 51 (7.84) | 13 / 51 / 18 | 0.0385 | −1.93 | 0.1343 | 0.61 |

(Ablation leads other than "full" are rounded to the hour in the evaluate output.)

Readings: river levels are the backbone (without them no alert fired in TEST or in 2024); upstream gauges buy the lead at Taquari (+20 → −1 h) and Porto Alegre (+7 → −1 h) and at Encantado (+17 → +7 h), and account for 14 of the 21 TEST false alarms (21 → 7 without them); INMET rain buys Muçum's lead (+26 → 0 h) and Porto Alegre's; ANA gauge rain adds 7 h at Muçum and 3 false alarms. **Freshness decay made calibration worse** (Brier 2024 0.0927 without it vs 0.1148 with it; TEST 0.0062 vs 0.0074) without changing any 2024 lead: when a gauge goes silent in a flood, the river is usually still high, so discounting its last reading throws away true evidence. Equal weights (plain naive Bayes) alerts earliest but has 2.4× the false alarms and is worse than climatology in TEST (BSS −1.93).

### Silent gauges in the 2024 replay (calibrated fusion)

Key hours chosen by `evaluate.key_hours` (each place's first alert, and its first hour at ≥ attention with its own gauge silent):

| Place | Kind | Local time | p | Level | Silent gauges |
|---|---|---|---|---|---|
| Estrela | first alert | 04-29 20:00 | 0.888 | alert | — |
| Encantado | first alert | 04-29 21:00 | 0.749 | alert | — |
| Taquari | first alert | 04-30 08:00 | 0.703 | alert | — |
| Muçum | first alert | 04-30 11:00 | 0.646 | alert | — |
| Encantado | own gauge silent | 05-01 01:00 | 0.988 | emergency | 86720000 |
| Estrela | own gauge silent | 05-01 20:00 | 0.999 | emergency | 86720000, 86879300 |
| Porto Alegre | first alert | 05-02 06:00 | 0.887 | alert | 87450020 (Gasômetro, not started) |
| Taquari | own gauge silent | 05-02 12:00 | 0.854 | alert | 86720000, 86950000 |
| Porto Alegre | own gauge silent | 05-03 03:00 | 0.956 | emergency | 86950000, 87450004, 87450020 |

### Alert agent (`alerts.py`; Qwen3-8B 4-bit via the local mlx-lm server, thinking off, temperature 0)

The agent gets the fused state rendered as text (probability, level, every signal with value, age, LR, reliability, log-odds effect and "probability without it", and the silent gauges) and returns `AlertDraft{headline, explanation, drivers, silent_gauges}`. It has no field for the probability or level: `Alert.probability/level` are copied from fusion. The **citation audit** is deterministic: every number in the headline/explanation must appear in the input block (up to the text's own rounding), every station code and place name must be in the input (river/valley/lake uses of "Taquari"/"Guaíba" excluded), each silent gauge must be named by code, or by place in a sentence that says it is silent/stale/not reporting, the `silent_gauges` field must equal the input's, and a stated risk level must be the fused one. With `--audit-retry` a failed audit is sent back to the model as a retry (Pydantic AI output validator). The audit checks grounding, not pairing: a real number attached to the wrong station would pass.

Smoke run (4 calls, `runs/m3/alerts_smoke.jsonl`, server shared with another job):

| Key hour | Output mode | Audit | Seconds | Note |
|---|---|---|---|---|
| Encantado, own gauge silent, 05-01 01:00 | tool | pass (6 numbers) | 16.7 | names 86720000 as silent for 3.5 h; cites effects +4.66 and +2.12 |
| Estrela, first alert, 04-29 20:00 | tool | pass (7 numbers) | 10.3 | "No gauges are silent." |
| Porto Alegre, 3 silent gauges, 05-03 03:00 | tool | **fail**: `silent_gauges` listed only 87450020, not 86950000 and 87450004 | 16.1 | the text called 87450004 "stale" but did not flag it as silent |
| same hour | prompted | pass (7 numbers) | 14.0 | lists all three; calls Gasômetro "upstream" (its role label in the input) |

Full run over the 9 key hours × 3 modes (`scripts/run_after_queue.sh`, after the shared server's queue; output
`runs/m3/alerts_queued.jsonl`, summary `runs/m3/alerts_queued_summary.json`; 27 runs, 0 errors):

| Mode | Audit pass | Model requests | Seconds (total / per alert) | Failure kinds |
|---|---|---|---|---|
| tool output | **9 / 9** | 9 | 104.8 / 11.6 | — |
| tool output + audit retry | **9 / 9** | 10 (one retry) | 172.2 / 19.1 | — |
| prompted output (JSON in text) | 7 / 9 | 9 | 149.4 / 16.6 | silent gauge not mentioned: 2 |

- The two prompted failures: Estrela 05-01 20:00 (did not say that Encantado 86720000 was silent; it listed it in
  `silent_gauges` but the text only called Estrela stale) and Porto Alegre 05-03 03:00 (did not say that Taquari
  86950000 was silent, again listed in the field only). Both are the hours with two or three silent gauges.
- The one retry was at Porto Alegre 05-03 03:00 (three silent gauges), the hour the tool mode failed in the smoke
  run; with the retry the final text passed. The JSONL keeps only the final draft, so which check failed on the
  first try is not recorded.
- Tool mode passed 9/9 without retries here, while it failed the same Porto Alegre hour in the smoke run (same
  temperature 0, server shared with another job both times): 1 smoke run is not enough to call a mode reliable.
- The audit checks grounding, not pairing (see above). A scratch pairing check (every number in a sentence that names
  a station code must appear on that station's input line or on the fused-probability line) found no mismatch in the
  27 texts; sentences that name a place but no code, and sentences with two codes, are only weakly checked by it. One
  text is ambiguous: "Encantado (86720000) and Estrela (86879300) also
  contributed significantly with effects of +2.46 each, increasing the probability from 16.8% to 70.3%" (Taquari
  04-30 08:00, tool), where 16.8% is the "without it" value of *each* gauge, not of both together.
- **Input bug found while reading the texts (fixed after the run):** `alerts.build_input` looked up a silent gauge's
  last reading by station code only, and ANA rain shares the code with ANA level. At Estrela 05-01 20:00 the silent
  line read "86720000 at Encantado: last reading 146 cm, 0 h ago", which is the 24 h *rain* total of that station; the
  signal list above it had the right values (1355 cm, 22.5 h old). It affected 1 of the 9 key hours (the only one
  where a silent gauge's rain signal has a larger effect than its level signal) and is one of the two prompted
  failures. Fixed in `build_input` (level signal only) with a regression test. Re-run of that hour after the fix
  (3 modes × 1 run, temperature 0, `runs/m3/alerts_rerun_estrela.jsonl`): tool, tool + audit retry and prompted all
  pass, 1 request each; the prompted text now says "The gauge at Encantado (86720000) has been silent for 22.5 hours".
  One run per mode, so this shows the fixed input can pass, not that the bug caused the failure.

Example texts (as generated; the agent's instructions ask for English, so the texts are in English):

1. Encantado, own gauge silent, 05-01 01:00 (fused p = 98.8 %, emergency), tool mode, **audit pass** (6 numbers):
   > **Encantado: EMERGENCY risk, 98.8% probability.** The risk estimate was primarily driven by the stale river
   > gauge at Encantado (86720000) with an effect of +4.66, which without it would lower the probability to 44.6%.
   > The fresh gauge at Muçum (86510000) with an effect of +2.12 also contributed significantly, reducing the
   > probability to 91.0% without it. Other signals, such as the rain stations at Bento Gonçalves (A840) and
   > Encantado (86720000), had smaller effects. The gauge at Encantado (86720000) has been silent for 3.5 hours, and
   > its last reading is being trusted less.
2. Porto Alegre, three silent gauges, 05-03 03:00 (p = 95.6 %, emergency), prompted mode, **audit fail**
   (`silent_not_mentioned: 86950000`):
   > **Porto Alegre: EMERGENCY risk with 95.6% flood probability.** The risk estimate was raised by the stale Porto
   > Alegre gauge (87450004) which increased the probability from 19.1% to 95.6%. The Guaíba gauge (87242000) also
   > contributed significantly, raising the probability from 72.5% to 95.6%. The Porto Alegre gauge (87450004) is
   > stale with a 3.8-hour-old reading, and the upstream Porto Alegre gauge (87450020) is missing and silent for 72
   > hours.

   The Taquari outlet gauge (86950000, last reading 18.2 h old) is in `silent_gauges` but not in the text.
3. Same hour, tool mode + audit retry, **audit pass after one retry** (2 requests, 11 numbers):
   > **Porto Alegre: EMERGENCY risk with 95.6% probability.** The risk estimate was primarily driven by the river
   > level at Porto Alegre (87450004) which, although stale, had a significant effect of +4.52, raising the
   > probability from 19.1% to 95.6%. The river level at Guaíba (87242000) also contributed with an effect of +2.12,
   > increasing the probability from 72.5% to 95.6%. The rain station at Canela (A879) added +1.04, and the rain
   > station at Porto Alegre (A801) added +0.70. The gauge at Taquari (86950000) had a smaller effect of +0.38. The
   > gauge at Porto Alegre (87450020) is silent, with no reading in 72 hours, and its absence had no effect on the
   > estimate.

   It passes because 86950000 is named by code (the audit accepts a code anywhere in the text), although the
   sentence does not say that gauge is silent: the code rule is looser than the place rule.

## Milestone 4: LLM-only fusion vs Bayesian fusion (2026-10-01)

Command: `make llm-fusion` (`python -m disaster_risk.llm_fusion prepare|run`), then `make llm-fusion-score`.
Outputs in `runs/m4/`: `llm_fusion_hours.json` (the pre-registered hour set with the exact snapshot text of every
hour and the prompt; written before the first model call), `llm_fusion_runs.jsonl`, `llm_fusion_summary.json`.

### Design (fixed before any model call)

- **Model:** Qwen3-8B 4-bit, local mlx-lm server (`default_model`), thinking off, **temperature 0.7, 3 samples per
  hour**, typed output `LLMRisk{probability, level, reason}` via a tool call (Pydantic AI).
- **Input per (place, hour):** the warning signals the calibrated fusion uses at that replay hour (same replay, so
  nothing after t): for each signal the value, status, age of the reading, calibrated LR, reliability (with the
  freshness decay), the band rule, and for level gauges p90 / p99 / official flood level; the silent gauges; the
  place's prior. **Not given:** the fused probability, log-odds, weights, risk level, labels, EMS products.
- **Prompt** (`llm_fusion.INSTRUCTIONS`, prompt version `llm-fusion-v1`, SHA `1321cf880a57da53`): the same for every
  hour; it states the hypothesis (own gauge at flood level within 24 h), what LR and reliability mean, and the level
  thresholds (0.10 / 0.50 / 0.90). Not tuned on outcomes; `run` refuses to start if the prompt changed after `prepare`.
- **Hours (147):** *event*: per place, every 3 h from −48 h to +12 h around the 2024 reference crossing, anchored on
  the replay hour at or before the crossing (21 × 5 = 105); *quiet_fa*: the onset hour of each of the 21 calibrated
  false-alarm episodes in TEST (Muçum 3, Encantado 7, Estrela 9, Taquari 1, Porto Alegre 1); *quiet_random*: the same
  number per place, drawn with seed 20240501 from TEST hours with label 0 and no reading ≥ flood level within ±72 h.
- **Calls:** 147 × 3 = 441 (under the ~600 budget, no grid reduction). 441 ok, 0 errors; model time 2,879.6 s,
  median 6.4 s per call (server shared with other jobs). 4 of 441 answers had a level inconsistent with their own
  probability (e.g. 0.42 labelled "alert"); the level the model stated is used for alerts.
- **Bayesian fusion** on the same hours: the calibrated "full" fusion of milestone 3. Leads below are on the 3-hour
  grid, so they differ from the hourly leads of milestone 3 (Encantado +15.25 vs +17.25 h: its alert started at 21:00,
  between grid hours; Taquari +15.25 vs +20.25 h: the fusion was on alert at 08:00 on 04-30 but at attention at the
  07:00 and 10:00 grid hours).

### Results

Alert lead time (first grid hour at ≥ alert; lead = crossing − that hour; the grid starts at −48 h, so +48.25 h means
"already on alert at the first grid hour"):

| Place | Crossing (local) | Bayesian fusion | LLM, each of 3 samples | LLM, mean of 3 p |
|---|---|---|---|---|
| Muçum | 05-01 12:45 | +24.75 h | +39.75 / +39.75 / +39.75 h | +39.75 h |
| Encantado | 04-30 14:15 | +15.25 h | +18.25 / +18.25 / +18.25 h | +18.25 h |
| Estrela | 04-30 08:15 | +12.25 h | +12.25 / +12.25 / +12.25 h | +12.25 h |
| Taquari | 05-01 04:15 | +15.25 h | +30.25 / +30.25 / +30.25 h | +30.25 h |
| Porto Alegre | 05-02 13:15 | +6.25 h | +48.25 / +48.25 / +48.25 h (censored) | +48.25 h |

The earlier LLM alerts are mostly alerts on hours whose label is 0 (no flood within 24 h):

| Event hours | n | Bayesian fusion ≥ alert | LLM ≥ alert (per sample) |
|---|---|---|---|
| label 0 (flood not within 24 h) | 45 | 1 | 16 / 16 / 15 |
| label 1 | 57 | 38 | 53 / 53 / 53 |
| no label (gauge silent) | 3 | — | — |

At Porto Alegre the LLM was on alert at 13:00 on 04-30, 48 h before the crossing, with the Cais Mauá gauge below its
p90 (it cited the upstream Taquari gauge and rain LRs); the fusion stayed below 0.10 until 05-01 16:00. At Muçum the
LLM went to alert at 04-29 21:00 (−39 h; fusion 0.127, attention), dropped to attention at −30 h and returned to
emergency at −27 h.

False alerts on the quiet set (hours at ≥ alert; no flood within 24 h in any of them):

| Quiet hours | n | Bayesian fusion ≥ alert | LLM ≥ alert (per sample) | LLM ≥ alert in any sample | LLM ≥ attention (per sample) |
|---|---|---|---|---|---|
| fusion false-alarm onsets (TEST) | 21 | 21 (by construction) | 17 / 17 / 16 | 17 | 21 / 21 / 21 |
| random quiet (TEST, matched per place) | 21 | 0 (1 at attention) | 0 / 0 / 0 | 0 | 1 / 3 / 2 |

The LLM repeats 16–17 of the fusion's 21 false alarms; the ones it declines are Estrela hours (2023-11-03, 2024-01-19,
2024-04-14, 2024-04-17, where it answered 0.22–0.32 in every sample; and 2023-07-08 in 1 of 3 samples).

Brier score against the fusion's label (same hours; this set over-samples floods and fusion false alarms, so the
numbers compare the two methods on these hours and are not comparable with milestone 3's Brier):

| Hours | n (positives) | Bayesian fusion | LLM, mean of 3 p | LLM, per sample |
|---|---|---|---|---|
| event | 102 (57) | **0.1195** | 0.1579 | 0.1621 / 0.1543 / 0.1608 |
| quiet (fa + random) | 42 (0) | **0.2132** | 0.2839 | 0.2849 / 0.2984 / 0.2740 |
| all | 144 (57) | **0.1469** | 0.1947 | 0.1979 / 0.1964 / 0.1938 |

Run-to-run consistency (3 samples at temperature 0.7, 147 hours): spread (max − min probability) median 0.03, p90
0.10, max 0.63 (Porto Alegre 04-30 16:00: 0.85 / 0.42 / 0.22); mean per-hour SD 0.017. Stated levels differ between
samples in 34 of 147 hours; whether the hour is at ≥ alert differs in 2 of 147.

The LLM's answers collapse onto a few values: 36 distinct probabilities in 441 answers; 0.85 (119 times), 0.92 (66),
0.82 (62) and 0.02 (52) make up 299 of 441. It never answered above 0.98, so at hours where the fusion said
0.99–1.00 and the river did flood it scored worse; its alert/no-alert decision is stable across samples, its
probability is a coarse label.

Readings: on the same inputs, the LLM alerts earlier at four of five places but does so by alerting at hours that did
not flood within 24 h (15–16 of 45 vs 1 of 45 for the fusion), repeats most of the fusion's false alarms, does not
alert on random quiet hours, and is worse calibrated (Brier 0.1947 vs 0.1469 overall). The 3-sample spread is small
(median 0.03) but not negligible at the boundary (34 hours with a level change between samples).
